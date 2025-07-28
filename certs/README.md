# SSL/TLS Certificates Directory

This directory is used to store SSL/TLS certificates for HTTPS deployment.

## Required Files

To enable HTTPS with the `--domain` parameter, place the following files in this directory:

1. **`tls.cer`** - The complete certificate chain (your certificate + intermediate certificates)
   - Must be in PEM format
   - Order: leaf certificate first, then intermediates
   
2. **`private.key`** - The private key for your certificate
   - Must be in PEM format
   - Must match the certificate in `tls.cer`

## Usage

```bash
# Deploy with HTTPS enabled
./deploy.sh --project-name=staging-new --environment=staging --domain=app.hotcalls.de

# Update only (including certificate updates)
./deploy.sh --project-name=staging-new --environment=staging --domain=app.hotcalls.de --update-only
```

## Security Notes

- **NEVER commit certificate files to git** - they are excluded by .gitignore
- Keep your private key secure and never share it
- These files should only exist on deployment machines

## Certificate Preparation

If you have separate certificate files, concatenate them in the correct order:

```bash
# Combine certificates (leaf first, then intermediates)
cat wildcard.cer intermediate1.cer intermediate2.cer > tls.cer
``` 