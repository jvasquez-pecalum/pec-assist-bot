# Azure VM Health Extension Fix

## Date
April 9, 2026

## VM Details
- **Name:** `vm-pec-n8n`
- **Resource Group:** `AI-Initiative-RG`
- **Location:** West US 2
- **OS:** Linux (Debian 12)

## Issue Description
VM health status showing **"Unhealthy"** in Azure Portal. Caddy server logs showed repeated health check requests returning `308 Permanent Redirect` status.

### Log Pattern Observed
```
caddy | {"level":"info","request":{"method":"GET","uri":"/"},"status":308,"resp_headers":{"Location":["https://localhost/"]}...}
```

**Source:** `ApplicationHealthExtension/1.0` (Azure VM monitoring)
**Frequency:** Every 5 seconds
**Problem:** Health checks using HTTP on port 80, but Caddy redirects all HTTP traffic to HTTPS

## Root Cause
Azure VM `HealthExtension` was configured with:
- Protocol: `http`
- Port: `80`
- Request Path: `/`

This caused health probes to receive a `308` redirect response instead of `200 OK`, resulting in the VM being marked as unhealthy.

## Solution
Updated the VM health extension to use HTTPS instead of HTTP.

### Steps Performed

1. **Accessed Azure Cloud Shell** (Bash)

2. **Verified current extension settings:**
   ```bash
   az vm extension show \
     --resource-group AI-Initiative-RG \
     --vm-name vm-pec-n8n \
     --name HealthExtension \
     --query settings
   ```
   
   Result:
   ```json
   {
     "intervalInSeconds": 5,
     "numberOfProbes": 5,
     "port": 80,
     "protocol": "http",
     "requestPath": "/"
   }
   ```

3. **Removed old extension:**
   ```bash
   az vm extension delete \
     --resource-group AI-Initiative-RG \
     --vm-name vm-pec-n8n \
     --name HealthExtension
   ```

4. **Installed new extension with HTTPS configuration:**
   ```bash
   az vm extension set \
     --resource-group AI-Initiative-RG \
     --vm-name vm-pec-n8n \
     --name ApplicationHealthLinux \
     --publisher Microsoft.ManagedServices \
     --version 2.0.19 \
     --settings '{"protocol": "https", "port": 443, "requestPath": "/", "intervalInSeconds": 5, "numberOfProbes": 5}'
   ```

## Verification

### Extension Configuration (Post-Fix)
```json
{
  "autoUpgradeMinorVersion": true,
  "name": "ApplicationHealthLinux",
  "provisioningState": "Succeeded",
  "settings": {
    "intervalInSeconds": 5,
    "numberOfProbes": 5,
    "port": 443,
    "protocol": "https",
    "requestPath": "/"
  },
  "typeHandlerVersion": "2.0"
}
```

### Expected Outcome
- Health checks now use `https://localhost:443/`
- Caddy should return `200 OK` instead of `308`
- VM health status should change from **Unhealthy** to **Healthy** within 1-2 minutes

## References
- Extension Publisher: `Microsoft.ManagedServices`
- Extension Name: `ApplicationHealthLinux`
- Extension Version: `2.0.19`
