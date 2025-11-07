# Security Guidelines

## ⚠️ IMPORTANT: Never Commit Secrets!

This project handles sensitive credentials. **NEVER** commit the following files:

- `telegram_config.env` - Contains real Telegram bot token
- `config.json` - Runtime configuration with sensitive settings
- `data/` directory - Contains user job data
- Any `.env` files (except `.env.template` files)

## 🔒 Secure Setup

### 1. Environment Configuration

**Always use environment variables for sensitive data:**

```bash
# Copy the template
cp server-dashboard.env.template /etc/server-dashboard.env

# Edit with your real credentials
sudo nano /etc/server-dashboard.env
```

**NEVER** hardcode:
- API tokens
- Bot tokens
- Passwords
- Personal paths (like `/home/username/...`)
- IP addresses of your server

### 2. Telegram Bot Security

Your Telegram bot token is a secret credential:

```bash
# Get token from @BotFather
# Add to /etc/server-dashboard.env
TELEGRAM_BOT_TOKEN=your_real_token_here
TELEGRAM_BOT_NAME=@YourBotName
```

**If you accidentally expose your token:**
1. Go to @BotFather on Telegram
2. Use `/revoke` command to revoke the token
3. Generate a new token
4. Update your configuration

### 3. Network Security

This dashboard is designed for **local network use only**:

- Access control middleware limits requests to local IPs (see `app.py:240`)
- Do NOT expose this directly to the internet without additional authentication
- Use a reverse proxy (nginx/Caddy) with authentication if internet access is needed
- Consider using VPN for remote access instead

### 4. File Permissions

Protect sensitive files:

```bash
# Secure environment file
sudo chmod 600 /etc/server-dashboard.env

# Secure data directory
chmod 700 data/
```

### 5. Sudo Configuration

The dashboard needs sudo access for service control. Create a sudoers file:

```bash
sudo visudo -f /etc/sudoers.d/server-dashboard
```

Add (replace `username` with your user):
```
username ALL=(ALL) NOPASSWD: /bin/systemctl start ollama
username ALL=(ALL) NOPASSWD: /bin/systemctl stop ollama
username ALL=(ALL) NOPASSWD: /bin/systemctl restart ollama
username ALL=(ALL) NOPASSWD: /bin/systemctl start comfyui
username ALL=(ALL) NOPASSWD: /bin/systemctl stop comfyui
username ALL=(ALL) NOPASSWD: /bin/systemctl restart comfyui
username ALL=(ALL) NOPASSWD: /bin/systemctl start sunshine
username ALL=(ALL) NOPASSWD: /bin/systemctl stop sunshine
username ALL=(ALL) NOPASSWD: /bin/systemctl restart sunshine
```

### 6. Docker Security

Whitelist only specific containers in the code:

```python
# In app.py
allowed_containers = ['open-webui', 'docket-converter']
```

Only allow control of trusted containers.

### 7. Input Validation

The application validates:
- Service names against whitelist
- Actions against allowed list
- Network access (local only)
- Job parameters

Do not remove these validations.

## 🐛 Reporting Security Issues

If you find a security vulnerability, please:

1. **Do NOT** open a public issue
2. Email the maintainer directly (see repository owner's profile)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## 📋 Security Checklist

Before deploying:

- [ ] All `.env` files are in `.gitignore`
- [ ] No tokens/passwords in code
- [ ] Environment template has placeholder values only
- [ ] File permissions are set correctly
- [ ] Sudo configuration is minimal and specific
- [ ] Network access is limited to local IPs
- [ ] Docker container whitelist is configured
- [ ] Backup credentials are stored securely

## 🔄 Regular Maintenance

- Update dependencies regularly: `pip install -r requirements.txt --upgrade`
- Review logs for suspicious activity: `sudo journalctl -u server-dashboard`
- Rotate Telegram bot tokens periodically
- Monitor failed login/access attempts

## 📚 Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security Best Practices](https://flask.palletsprojects.com/en/latest/security/)
- [Telegram Bot Security](https://core.telegram.org/bots/security)
