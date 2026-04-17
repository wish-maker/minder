# Security Policy

## Supported Versions

Currently supported versions:
- **Version 2.0.0** (Current) - Security updates
- **Version 1.x** - Maintenance only (no new features)

## Reporting a Vulnerability

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please send an email to: **security@example.com**

Please include:
- **Description**: Clear description of the vulnerability
- **Steps to reproduce**: Detailed steps to reproduce the issue
- **Impact**: Potential impact of the vulnerability
- **Proof of Concept**: If available, include a PoC
- **Affected versions**: Which versions are affected

### Response Timeline

- **Initial response**: Within 48 hours
- **Detailed response**: Within 7 days
- **Resolution**: As soon as feasible, based on severity

### What Happens Next

1. **Confirmation**: We'll acknowledge receipt of your report
2. **Investigation**: We'll investigate the issue
3. **Resolution**: We'll work on a fix
4. **Disclosure**: We'll coordinate disclosure with you

## Security Features

Minder includes several security features:

### Authentication
- JWT-based authentication with bcrypt password hashing
- Configurable token expiration (default: 30 minutes)
- Secure password requirements (min 8 characters)

### Authorization
- Role-based access control (admin/user/readonly)
- API endpoint permissions
- Plugin-level permissions

### Network Security
- Network-aware rate limiting
- CORS configuration
- Trusted network detection (Local/VPN/Public)
- IP-based access control

### Input Validation
- SQL injection prevention
- XSS protection
- Command injection prevention
- Input sanitization

### Data Protection
- Encrypted passwords (bcrypt)
- Secure environment variable handling
- Database connection encryption
- TLS/SSL support

### Plugin Security
- Plugin security levels (strict/moderate/permissive)
- Trusted/blocked author lists
- Plugin signature verification (optional)
- Size limits for plugin packages

## Security Best Practices

### For Users

1. **Use strong passwords**: Minimum 32 characters for JWT_SECRET_KEY
2. **Enable HTTPS**: Use reverse proxy with SSL in production
3. **Limit network access**: Configure firewall rules
4. **Regular updates**: Keep dependencies updated
5. **Monitor logs**: Review access logs regularly
6. **Backup data**: Regular automated backups
7. **Use secrets management**: Don't commit secrets to git

### For Developers

1. **Never commit secrets**: Use environment variables
2. **Validate input**: Always validate user input
3. **Use parameterized queries**: Prevent SQL injection
4. **Sanitize output**: Prevent XSS attacks
5. **Follow principle of least privilege**: Minimize permissions
6. **Keep dependencies updated**: Regular security updates
7. **Use secure coding practices**: Follow OWASP guidelines

### For Production

1. **Enable rate limiting**: Prevent abuse and DoS attacks
2. **Use HTTPS**: Encrypt all traffic
3. **Configure CORS properly**: Limit allowed origins
4. **Monitor security logs**: Set up alerting
5. **Regular security audits**: Periodic security reviews
6. **Implement backup strategy**: Disaster recovery planning
7. **Use secrets management**: Vault, AWS Secrets Manager, etc.

## Security Configuration

### Environment Variables

```bash
# Authentication
JWT_SECRET_KEY=<32-char-random-string>
JWT_EXPIRE_MINUTES=30

# Plugin Security
PLUGIN_SECURITY_LEVEL=moderate  # strict|moderate|permissive
PLUGIN_TRUSTED_AUTHORS=
PLUGIN_BLOCKED_AUTHORS=
PLUGIN_REQUIRE_SIGNATURE=false
PLUGIN_MAX_SIZE_MB=10

# Network Security
LOCAL_NETWORK_CIDR=192.168.68.0/24
TAILSCALE_CIDR=100.64.0.0/10
TRUST_LOCAL_NETWORK=true
TRUST_VPN_NETWORK=true
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### Rate Limiting

- **Local Network**: Unlimited access
- **VPN/Tailscale**: 200 requests/hour
- **Public Network**: 50 requests/hour

## Known Security Issues

### Past Vulnerabilities

See [CHANGELOG.md](CHANGELOG.md) for security fixes in each version.

### Current Limitations

1. **Plugin System**: Plugins run in same process (isolation in progress)
2. **File Upload**: No virus scanning (use in trusted environments only)
3. **Session Management**: No session revocation (requires restart)

## Security Audits

Minder has not yet undergone a professional security audit. We plan to conduct one before the 3.0 release.

## Dependencies

We regularly update dependencies for security patches. See [requirements.txt](requirements.txt) for current versions.

## Contact

For security-related questions or concerns:
- **Email**: security@example.com
- **PGP Key**: Available on request

---

Thank you for helping keep Minder secure! 🛡️
