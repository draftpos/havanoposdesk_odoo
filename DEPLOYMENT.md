# Auto Deployment Setup Guide

This repository includes a GitHub Actions workflow in `.github/workflows/deploy.yml` that automatically deploys the latest code to your server whenever commits are pushed or merged into `main` or `master`.

---

## 1. Configure GitHub Repository Secrets

Go to your repository on GitHub:
**Settings** > **Secrets and variables** > **Actions** > **New repository secret**

Add the following secrets:

| Secret Name | Required | Description | Example |
| :--- | :---: | :--- | :--- |
| `SERVER_HOST` | **Yes** | Server IP address or domain | `198.51.100.25` or `odoo.example.com` |
| `SERVER_USER` | **Yes** | SSH user on the server | `ubuntu` / `root` / `odoo` |
| `SERVER_SSH_KEY` | **Yes** | SSH Private Key (ED25519 or RSA) | Entire content of `~/.ssh/id_rsa` or deploy key |
| `SERVER_PORT` | No | SSH Port (defaults to `22` if omitted) | `22` |
| `SERVER_TARGET_DIR` | No | Full path to this addon folder on the server (defaults to `/opt/odoo/custom-addons/havanoposdesk_odoo`) | `/opt/odoo/custom-addons/havanoposdesk_odoo` |
| `UPGRADE_MODULE` | No | Set to `true` if you want automatic `-u havanoposdesk_odoo` | `false` |
| `ODOO_DB_NAME` | No | Odoo database name (if `UPGRADE_MODULE` is enabled) | `production_db` |

---

## 2. Server Preparation

Run these steps once on your target server:

### A. Add the Deploy Key to Authorized Keys
```bash
# Generate key pair (if not already done)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy_key

# Authorize the key
cat ~/.ssh/github_deploy_key.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh

# Copy the private key output to paste into GitHub Secret `SERVER_SSH_KEY`
cat ~/.ssh/github_deploy_key
```

### B. Allow Passwordless Service Restart (if non-root user)
If your SSH user is not `root`, allow it to restart Odoo without being prompted for a password:
```bash
sudo visudo
```
Add this line at the bottom:
```sudoers
your_username ALL=(ALL) NOPASSWD: /bin/systemctl restart odoo, /bin/systemctl restart odoo-server
```

---

## 3. Triggering Deployments

- **Automatic**: Any `git push` or PR merge into `main` or `master` triggers a deploy.
- **Manual**: Navigate to **Actions** in GitHub, select **Auto Deploy to Server**, click **Run workflow**, and optionally specify options (e.g. database upgrade or restart).
