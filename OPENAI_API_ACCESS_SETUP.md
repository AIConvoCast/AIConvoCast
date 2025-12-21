# How to Grant API Access to GPT-5.2 Models on OpenAI Website

This guide provides step-by-step instructions for ensuring your OpenAI API key has access to GPT-5.2 models (including Model ID 164: `gpt-5.2-chat-latest`).

---

## Step 1: Log into OpenAI Platform

1. Go to the OpenAI Platform: **https://platform.openai.com/**
2. Log in with your OpenAI account credentials
3. Ensure you're on the correct account/organization if you have multiple

---

## Step 2: Verify Your API Key Status

### 2.1 Navigate to API Keys Page

1. Click on your **profile icon** (top right corner)
2. Select **"API keys"** from the dropdown menu
   - Or go directly to: **https://platform.openai.com/api-keys**

### 2.2 Check Your API Key

1. Locate your API key in the list (it will show as `sk-...` with most characters hidden)
2. Verify the key status:
   - ✅ **Active** - Key is working
   - ⚠️ **Expired** - Create a new key
   - ❌ **Revoked** - Create a new key

### 2.3 Create/Manage API Keys (If Needed)

**To create a new API key:**
1. Click **"Create new secret key"** button
2. Give it a descriptive name (e.g., "Podcast Workflow Key")
3. **Copy the key immediately** - you won't be able to see it again
4. Save it securely in your `.env` file or GitHub secrets

**Important Notes:**
- API keys have **full access** to all models available to your account by default
- You cannot restrict model access per API key
- Model access is determined by your **account tier/plan**, not API key permissions

---

## Step 3: Check Account Usage and Limits

### 3.1 View Usage Dashboard

1. Navigate to: **https://platform.openai.com/account/usage**
2. Review your:
   - Current usage statistics
   - Available credits/quota
   - Billing information

### 3.2 Check Account Limits

1. Navigate to: **https://platform.openai.com/account/limits**
2. Review:
   - Rate limits per model
   - Request limits
   - Token limits
   - Model access permissions

**Note:** GPT-5.2 models may have different rate limits than older models.

---

## Step 4: Verify Model Availability

### 4.1 Check Models Documentation

1. Go to: **https://platform.openai.com/docs/models**
2. Search for "GPT-5.2" or "gpt-5.2"
3. Review:
   - Which GPT-5.2 models are available
   - Any requirements or restrictions
   - Pricing information

### 4.2 Check Model Access via API

You can programmatically check which models you have access to:

**Python Method:**
```python
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
models = client.models.list()

gpt52_models = [m.id for m in models.data if 'gpt-5.2' in m.id.lower()]
print("Available GPT-5.2 models:", gpt52_models)
```

---

## Step 5: Enable Access to New Models (If Not Available)

### 5.1 Check for Early Access Requirements

Some newer models may require:

1. **Account Tier/Plan Upgrade:**
   - Go to: **https://platform.openai.com/account/billing**
   - Review pricing: **https://openai.com/pricing**
   - Upgrade if necessary to access premium models

2. **Early Access Approval:**
   - Check OpenAI blog: **https://openai.com/blog**
   - Look for announcements about GPT-5.2 availability
   - Some models may require waitlist signup

### 5.2 Request Access (If Needed)

If GPT-5.2 models don't appear in your available models:

1. **Contact OpenAI Support:**
   - Go to: **https://help.openai.com/**
   - Submit a support request
   - Explain you need access to GPT-5.2 models
   - Include your account email and use case

2. **Check Status Page:**
   - Visit: **https://status.openai.com/**
   - Check for any service disruptions or availability issues

3. **Review Organization Settings:**
   - Go to: **https://platform.openai.com/account/org-settings**
   - If using an organization, ensure you have proper permissions
   - Check if model access is restricted at the org level

---

## Step 6: Configure Model Access in Your Code

Once you have API access confirmed, update your environment variables:

### 6.1 Local Development (.env file)

```env
OPENAI_API_KEY=sk-your-api-key-here
```

### 6.2 GitHub Actions (Secrets)

1. Go to your repository: **Settings** → **Secrets and variables** → **Actions**
2. Add or update `OPENAI_API_KEY` secret
3. Paste your API key value

### 6.3 Verify Configuration

Test that your API key works:

```python
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
models = client.models.list()
print(f"API key configured. Found {len(models.data)} models.")
```

---

## Step 7: Understanding Model Access Control

### Important Notes:

1. **API Keys Don't Restrict Models:**
   - API keys themselves don't control which models you can access
   - Model access is based on your account tier/plan
   - All active API keys have the same model access

2. **Account-Level Restrictions:**
   - Your account's billing plan determines model availability
   - Some models require paid accounts
   - Usage limits are account-wide, not per-API-key

3. **Organization Settings:**
   - If you're in an organization, admins may restrict model access
   - Check organization settings if models aren't available

---

## Troubleshooting

### Issue: Model not found in available models list

**Possible Causes:**
- Model not available in your account tier
- Regional restrictions
- Model requires early access approval
- Account needs upgrade

**Solutions:**
1. Check your account tier at https://platform.openai.com/account/usage
2. Review model documentation for requirements
3. Contact OpenAI support for assistance
4. Check if organization settings are restricting access

### Issue: "Insufficient quota" error

**Solutions:**
1. Add credits: https://platform.openai.com/account/billing
2. Check usage limits: https://platform.openai.com/account/limits
3. Wait for quota reset if on a usage-based plan

### Issue: "Rate limit exceeded" error

**Solutions:**
1. Check rate limits: https://platform.openai.com/account/rate-limits
2. Implement exponential backoff in your code
3. Reduce request frequency
4. Consider upgrading plan for higher rate limits

### Issue: "Permission denied" error

**Solutions:**
1. Verify API key is active: https://platform.openai.com/api-keys
2. Check organization permissions if applicable
3. Ensure API key hasn't been revoked
4. Create a new API key if needed

---

## Quick Checklist

Use this checklist to ensure proper API access:

- [ ] Logged into OpenAI Platform
- [ ] API key is active and not expired
- [ ] API key is saved in `.env` file (local) or GitHub secrets (CI/CD)
- [ ] Account has sufficient credits/quota
- [ ] Checked account usage dashboard
- [ ] Verified model appears in available models list
- [ ] Tested API call successfully
- [ ] Reviewed rate limits and usage limits
- [ ] Contacted support if model access issues persist

---

## Additional Resources

- **OpenAI Platform Dashboard**: https://platform.openai.com/
- **API Documentation**: https://platform.openai.com/docs
- **Models Documentation**: https://platform.openai.com/docs/models
- **API Reference**: https://platform.openai.com/docs/api-reference
- **Support Center**: https://help.openai.com/
- **Status Page**: https://status.openai.com/
- **Pricing**: https://openai.com/pricing

---

## Summary

**Key Points:**
1. API keys don't need special permissions for models - access is account-based
2. Model availability depends on your account tier/plan
3. Always verify model access by checking the available models list
4. Contact OpenAI support if you believe you should have access but don't

**For Model ID 164 (`gpt-5.2-chat-latest`):**
- If the model appears in your available models list → ✅ You have access
- If it doesn't appear → Check account tier, contact support, or wait for availability

---

*Last Updated: Based on OpenAI Platform as of 2025*

