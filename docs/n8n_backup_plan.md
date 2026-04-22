# n8n Workflow Backup to GitHub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an n8n workflow on the Azure VM that autonomously exports all active n8n workflows as JSON files, commits them to a dedicated GitHub repo, and runs on a daily schedule (plus on-demand).

**Architecture:** The n8n instance at `pecn8n.westus2.cloudapp.azure.com:9443` calls its own local API to list and fetch active workflows, writes each as a pretty-printed JSON file to a git-tracked directory on the Azure VM, then runs a shell command to `git commit` (only if files changed) and `git push` to a new dedicated GitHub repo. Idempotency is guaranteed by checking `git diff --cached --quiet` before committing.

**Tech Stack:** n8n MCP tools (`n8n_create_workflow`), n8n nodes (Schedule Trigger, Manual Trigger, Merge, HTTP Request, Split In Batches, Code, Execute Command), GitHub, bash/git on Azure VM.

---

## Prerequisites (Manual Steps — Do These First)

These must be done by SSH-ing into the Azure VM before the n8n workflow is created.

- [ ] **Step 1: Create the GitHub repo**

  Go to GitHub and create a new **public or private** repo named `n8n-workflow-backups` under the `pecalum` org or personal account. Initialize it with a README.

- [ ] **Step 2: SSH into the Azure VM**

  ```bash
  ssh azureuser@pecn8n.westus2.cloudapp.azure.com
  ```

- [ ] **Step 3: Set up the backup directory as a git repo**

  ```bash
  mkdir -p ~/n8n-workflow-backups
  cd ~/n8n-workflow-backups
  git init
  git remote add origin https://github.com/<YOUR_ORG>/n8n-workflow-backups.git
  git pull origin main
  ```

- [ ] **Step 4: Configure git credentials on the VM (Personal Access Token)**

  Create a GitHub PAT with `repo` scope, then configure git to use it:

  ```bash
  git config --global user.name "PEC Assist Bot"
  git config --global user.email "julio.pecalum@gmail.com"
  git config --global credential.helper store
  # Run a git push once to cache credentials:
  echo "# n8n Workflow Backups" > README.md
  git add README.md
  git commit -m "chore: initialize backup repo"
  git push -u origin main
  # Enter your GitHub username and PAT when prompted — stored permanently
  ```

- [ ] **Step 5: Get the n8n API Key**

  In the n8n UI: **Settings → n8n API → Create an API key**. Copy the key.

  Save it as an environment variable in the n8n `.env` file on the VM:

  ```bash
  # Edit ~/ai-initiative/.env (or wherever n8n docker-compose is)
  echo 'N8N_API_KEY=<YOUR_KEY_HERE>' >> ~/ai-initiative/.env
  # Restart n8n so it picks up the variable:
  cd ~/ai-initiative && docker compose restart n8n
  ```

---

## Task 1: Create the Backup Workflow via MCP

**Files:** No local files — this creates an n8n workflow via the MCP tool.

### Workflow Node Design

```
[Schedule Trigger] ─┐
                     ├─► [Merge] ─► [HTTP: List Workflows] ─► [Split In Batches] ─+─► [HTTP: Get Full Workflow] ─► [Code: Build filename] ─► [Execute: Write JSON file] ─► (loop back)
[Manual Trigger]  ─┘                                                               └─► [Execute: Git add+commit+push]
                                                                                    (done output)
```

- [ ] **Step 1: Create the workflow using MCP `n8n_create_workflow`**

  Call the MCP tool with this exact node and connection configuration:

  **Nodes array:**

  ```json
  [
    {
      "id": "node-schedule",
      "name": "Schedule Trigger",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [0, 200],
      "parameters": {
        "rule": {
          "interval": [{ "field": "hours", "hoursInterval": 24 }]
        }
      }
    },
    {
      "id": "node-manual",
      "name": "Manual Trigger",
      "type": "n8n-nodes-base.manualTrigger",
      "typeVersion": 1,
      "position": [0, 400],
      "parameters": {}
    },
    {
      "id": "node-merge",
      "name": "Merge Triggers",
      "type": "n8n-nodes-base.merge",
      "typeVersion": 3,
      "position": [220, 300],
      "parameters": { "mode": "chooseBranch", "chooseBranch": { "mode": "waitForAll" } }
    },
    {
      "id": "node-list",
      "name": "List Active Workflows",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [440, 300],
      "parameters": {
        "method": "GET",
        "url": "http://localhost:5678/api/v1/workflows",
        "sendQuery": true,
        "queryParameters": {
          "parameters": [{ "name": "active", "value": "true" }, { "name": "limit", "value": "100" }]
        },
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [{ "name": "X-N8N-API-KEY", "value": "={{ $env.N8N_API_KEY }}" }]
        },
        "options": {}
      }
    },
    {
      "id": "node-extract",
      "name": "Extract Workflow List",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [660, 300],
      "parameters": {
        "jsCode": "return $input.first().json.data.map(w => ({ json: w }));"
      }
    },
    {
      "id": "node-split",
      "name": "Loop Over Workflows",
      "type": "n8n-nodes-base.splitInBatches",
      "typeVersion": 3,
      "position": [880, 300],
      "parameters": { "batchSize": 1, "options": {} }
    },
    {
      "id": "node-get",
      "name": "Get Full Workflow",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [1100, 180],
      "parameters": {
        "method": "GET",
        "url": "=http://localhost:5678/api/v1/workflows/{{ $json.id }}",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [{ "name": "X-N8N-API-KEY", "value": "={{ $env.N8N_API_KEY }}" }]
        },
        "options": {}
      }
    },
    {
      "id": "node-code",
      "name": "Build File Content",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [1320, 180],
      "parameters": {
        "jsCode": "const wf = $input.first().json;\nconst safeName = wf.name.replace(/[^a-zA-Z0-9_-]/g, '_');\nconst filename = `${safeName}__${wf.id}.json`;\nconst content = JSON.stringify(wf, null, 2);\nreturn [{ json: { filename, content } }];"
      }
    },
    {
      "id": "node-write",
      "name": "Write Workflow to Disk",
      "type": "n8n-nodes-base.executeCommand",
      "typeVersion": 1,
      "position": [1540, 180],
      "parameters": {
        "command": "=printf '%s' {{ $json.content.replace(/'/g, \"'\\\\''\").__toJSON() }} > /home/azureuser/n8n-workflow-backups/{{ $json.filename }}"
      }
    },
    {
      "id": "node-git",
      "name": "Git Commit and Push",
      "type": "n8n-nodes-base.executeCommand",
      "typeVersion": 1,
      "position": [1100, 420],
      "parameters": {
        "command": "cd /home/azureuser/n8n-workflow-backups && git add -A && git diff --cached --quiet && echo 'No changes to commit' || (git commit -m \"chore: backup workflows $(date -u +%Y-%m-%dT%H:%M:%SZ)\" && git push origin main)"
      }
    }
  ]
  ```

  **Connections object:**

  ```json
  {
    "Schedule Trigger": { "main": [[{ "node": "Merge Triggers", "type": "main", "index": 0 }]] },
    "Manual Trigger": { "main": [[{ "node": "Merge Triggers", "type": "main", "index": 1 }]] },
    "Merge Triggers": { "main": [[{ "node": "List Active Workflows", "type": "main", "index": 0 }]] },
    "List Active Workflows": { "main": [[{ "node": "Extract Workflow List", "type": "main", "index": 0 }]] },
    "Extract Workflow List": { "main": [[{ "node": "Loop Over Workflows", "type": "main", "index": 0 }]] },
    "Loop Over Workflows": {
      "main": [
        [{ "node": "Get Full Workflow", "type": "main", "index": 0 }],
        [{ "node": "Git Commit and Push", "type": "main", "index": 0 }]
      ]
    },
    "Get Full Workflow": { "main": [[{ "node": "Build File Content", "type": "main", "index": 0 }]] },
    "Build File Content": { "main": [[{ "node": "Write Workflow to Disk", "type": "main", "index": 0 }]] },
    "Write Workflow to Disk": { "main": [[{ "node": "Loop Over Workflows", "type": "main", "index": 0 }]] }
  }
  ```

  **Settings:**
  ```json
  {
    "executionOrder": "v1",
    "saveDataErrorExecution": "all",
    "saveDataSuccessExecution": "all",
    "timezone": "UTC"
  }
  ```

- [ ] **Step 2: Verify the workflow was created**

  Call `n8n_list_workflows` and confirm "n8n Backup to GitHub" appears in the list.

---

## Task 2: Activate and Test the Workflow

- [ ] **Step 1: Activate the workflow**

  Call `mcp__n8n-mcp-full__n8n_update_partial_workflow` with `{ "active": true }` on the workflow ID returned from Task 1.

- [ ] **Step 2: Run the workflow manually via MCP**

  In the n8n UI, click "Execute Workflow" on the "n8n Backup to GitHub" workflow. Watch for:
  - "List Active Workflows" returns 4+ workflows
  - Loop runs once per workflow
  - Each JSON file appears in `~/n8n-workflow-backups/` on the VM
  - "Git Commit and Push" node exits 0

- [ ] **Step 3: Verify files are on GitHub**

  Open the GitHub repo in browser and confirm JSON files are present with workflow names like `PEC-Intake__3CpsxZLMLHAXPnFz.json`.

- [ ] **Step 4: Run a second time to verify idempotency**

  Trigger manually again. The "Git Commit and Push" node should output `No changes to commit` (exit 0, no new commit created in GitHub).

---

## Task 3: Add a `.gitignore` and `README.md` to the Backup Repo

- [ ] **Step 1: SSH into Azure VM and add a README**

  ```bash
  cd ~/n8n-workflow-backups
  cat > README.md << 'EOF'
  # n8n Workflow Backups

  Auto-generated exports of all active n8n workflows from the PEC Assist n8n instance.
  Updated daily by the "n8n Backup to GitHub" workflow.

  ## Format
  Each file is named `<WorkflowName>__<WorkflowID>.json` and contains the full n8n workflow JSON.

  ## How to restore
  Import any `.json` file via n8n UI: Settings → Import Workflow.
  EOF
  git add README.md
  git commit -m "docs: add README for backup repo"
  git push origin main
  ```

---

## Verification

1. **Workflow exists in n8n**: `n8n_list_workflows` returns "n8n Backup to GitHub"
2. **Files on VM**: SSH in and run `ls ~/n8n-workflow-backups/` — see one JSON per active workflow
3. **Files on GitHub**: Browse to the `n8n-workflow-backups` repo — same files present
4. **Idempotent**: Run workflow twice in a row — second run shows "No changes to commit", GitHub has only 1 new commit
5. **Scheduled**: Check n8n execution history the next day — automatic run at the configured interval

---

## Known Constraints & Notes

- **Execute Command node** requires n8n to run as a user that has git configured — `azureuser` on Azure VM already has this after the prerequisite steps.
- **n8n API key** must be set as `N8N_API_KEY` env var in n8n's Docker container via `.env` file — n8n exposes `$env` variables from its process environment.
- The **Merge node** with `waitForAll` mode waits for both triggers to fire simultaneously — this may cause issues. Alternative: use two separate workflow triggers connected directly to "List Active Workflows" without merging (n8n allows multiple triggers natively). If Merge causes issues, remove it and connect both triggers directly to "List Active Workflows".
- The `printf '%s'` write command handles most JSON content safely. If a workflow name has unusual characters, the `Build File Content` Code node's `safeName` regex replaces them with underscores.
