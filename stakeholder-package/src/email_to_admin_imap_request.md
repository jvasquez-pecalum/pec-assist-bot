# Email Request: IMAP Access for PEC Assist Service Account

---

**To:** IT Admin / Microsoft 365 Tenant Administrator  
**From:** jvasquez@pecalum.com  
**Subject:** Request: Enable IMAP access for pec.assist@pecalum.com (PEC Assist Teams Bot)

---

Hi,

I'm working on the **PEC Assist Teams Bot** project — the AI-powered IT helpdesk assistant that creates Asana tickets and sends auto-replies from `pec.assist@pecalum.com`.

**What I need:**
IMAP access enabled for the `pec.assist@pecalum.com` mailbox so our service can read incoming emails automatically.

**Context:**
Microsoft disabled Basic Authentication for IMAP across most tenants in 2022. Our current IMAP login attempts fail with `LOGIN failed` because the tenant is blocking legacy auth. We need your help to enable automated email ingestion.

**There are two ways to solve this — please let me know which approach your team prefers:**

---

### Option A: OAuth2 IMAP (Recommended by Microsoft)

This is the modern, secure approach. It requires a one-time setup:

1. **Register an app** in Microsoft Entra ID (Azure AD)  
   → Name: `PEC-Assist-IMAP-Reader`

2. **Grant API permission:**  
   → Office 365 Exchange Online → Application permission → `IMAP.AccessAsApp`

3. **Grant admin consent** for the permission

4. **Authorize the app** to access only the `pec.assist@pecalum.com` mailbox:  
   ```powershell
   Connect-ExchangeOnline
   New-ApplicationAccessPolicy -AppId <client-id> `
     -PolicyScopeGroupId pec.assist@pecalum.com `
     -AccessRight RestrictAccess `
     -Description "PEC Assist IMAP OAuth access"
   ```

5. Send me the **Client ID**, **Tenant ID**, and **Client Secret** so I can configure the service.

---

### Option B: Enable Basic Auth IMAP (Legacy)

If OAuth2 is not feasible short-term, the alternative is to allow Basic Authentication for IMAP at the tenant level:

1. **Enable IMAP** on the `pec.assist@pecalum.com` mailbox:  
   → Exchange Admin Center → Recipients → Mailboxes → pec.assist → Mailbox features → IMAP: **Enabled**

2. **Allow Basic Auth for IMAP** at the tenant level:  
   → Exchange Admin Center → Settings → Org settings → Modern authentication → Enable **IMAP** under basic auth protocols

3. Ensure the account uses an **App Password** (if MFA is enabled)

> ⚠️ Microsoft is phasing out Basic Auth entirely by April 2026, so this is a temporary solution.

---

**Current status of the service:**
- ✅ Asana task creation — working
- ✅ SMTP auto-reply — working
- ✅ OpenAI classification — working
- ❌ IMAP email reading — blocked (this request)

Once IMAP is enabled, the bot will be able to:
1. Poll for unread emails
2. Classify requests with AI
3. Create Asana tickets automatically
4. Send confirmation replies

Please let me know which option works best for your team, or if you'd like to schedule a quick call to discuss.

Thanks,

[Your name]
jvasquez@pecalum.com

---
