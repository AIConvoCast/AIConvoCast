# GitHub Environment Setup Guide

This guide will help you set up GitHub Environments for your AI podcast pipeline.

## What are GitHub Environments?

GitHub Environments allow you to:
- **Organize secrets and variables** by environment (production, staging, etc.)
- **Add protection rules** (required reviewers, wait timers)
- **Control deployments** with environment-specific configurations
- **Use variables instead of secrets** for non-sensitive data

## Step 1: Create the Environment

1. **Go to your GitHub repository**
2. **Click Settings tab**
3. **Click "Environments"** in the left sidebar
4. **Click "New environment"**
5. **Name it**: `production`
6. **Click "Configure environment"**

## Step 2: Add Environment Variables

In your `production` environment, add these **variables**:

### Required Variables

| Variable Name | Value | Description |
|---------------|-------|-------------|
| `OPENAI_API_KEY` | `sk-ESFy8Dn...` | Your OpenAI API key |
| `ELEVENLABS_API_KEY` | `sk_c7b2bab...` | Your Eleven Labs API key |
| `SHARE_SHEET_WITH_EMAIL` | `AIConvoCast@gmail.com` | Email for Google Sheets access |

### Required Secrets

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `GOOGLE_CREDS_JSON` | `{entire JSON content}` | Complete Google service account JSON |

## Step 3: Add Protection Rules (Optional)

You can add protection rules to your environment:

1. **Required reviewers**: Require approval before running workflows
2. **Wait timer**: Add a delay before deployment
3. **Deployment branches**: Restrict which branches can deploy

## Step 4: Test the Environment

1. **Go to Actions tab**
2. **Run "Test Setup" workflow**
3. **Verify all environment variables are detected**

## Environment vs Repository Secrets

### Use Environment Variables for:
- ✅ **Non-sensitive data** (email addresses)
- ✅ **Configuration values** that might change
- ✅ **Data that can be visible** in logs

### Use Environment Secrets for:
- ✅ **API keys** (OpenAI, Eleven Labs)
- ✅ **Service account credentials** (Google JSON)
- ✅ **Any sensitive data** that should be encrypted

## Current Configuration

Your workflows are now configured to use:

```yaml
environment: production
```

This means they will:
1. **Use the `production` environment**
2. **Access variables** via `${{ vars.VARIABLE_NAME }}`
3. **Access secrets** via `${{ secrets.SECRET_NAME }}`
4. **Respect protection rules** if configured

## Troubleshooting

### "Environment not found" error
- **Solution**: Make sure the environment name matches exactly
- **Check**: Environment names are case-sensitive

### "Variable not found" error
- **Solution**: Verify the variable is added to the environment
- **Check**: Variable names are case-sensitive

### "Secret not found" error
- **Solution**: Verify the secret is added to the environment
- **Check**: Secret names are case-sensitive

## Benefits of Using Environments

1. **Better Organization**: Separate production from development
2. **Security**: Environment-specific protection rules
3. **Flexibility**: Different configurations per environment
4. **Audit Trail**: Track who approved deployments
5. **Control**: Require approvals for production changes

## Next Steps

After setting up the environment:

1. **Test the setup** with the "Test Setup" workflow
2. **Run the Google credentials test**
3. **Try the main pipeline** workflow
4. **Monitor the logs** to ensure everything works

Your AI podcast pipeline is now properly configured with GitHub Environments! 