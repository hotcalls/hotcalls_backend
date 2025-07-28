# HTTPS Deployment Guide

This guide explains how to deploy the application with HTTPS support using the `--domain` parameter.

## Prerequisites

1. **SSL Certificate Files**
   - `certs/tls.cer` - Complete certificate chain (leaf + intermediates)
   - `certs/private.key` - Private key file

2. **Domain Name**
   - A domain or subdomain that you control
   - Ability to update DNS A records

## Step 1: Prepare Certificates

Place your certificate files in the `certs/` directory:

```bash
# Copy your certificate files
cp /path/to/your/certificate-chain.cer certs/tls.cer
cp /path/to/your/private.key certs/private.key

# Test the certificates (optional)
cd certs && ./test-certificates.sh && cd ..
```

## Step 2: Deploy with HTTPS

### New Deployment
```bash
./deploy.sh --project-name=staging-new --environment=staging --domain=app.hotcalls.de
```

### Update Existing Deployment
```bash
./deploy.sh --project-name=staging-new --environment=staging --domain=app.hotcalls.de --update-only
```

## Step 3: Update DNS

After deployment, the script will show the external IP address. Update your DNS:

1. Log into your DNS provider (IONOS, Cloudflare, etc.)
2. Create or update an A record:
   - Name: `app` (or your subdomain)
   - Type: `A`
   - Value: The IP address shown by the deployment script
   - TTL: 300 (5 minutes) or your preference

## Step 4: Verify HTTPS

Once DNS propagates (usually within minutes):

1. Visit `https://your-domain.com` in a browser
2. Check for the padlock icon
3. Verify the certificate details

## Troubleshooting

### Certificate Issues
- Ensure `tls.cer` contains the full chain (leaf first)
- Verify private key matches: `cd certs && ./test-certificates.sh`
- Check certificate expiry date

### DNS Issues
- Use `nslookup your-domain.com` to verify DNS resolution
- Wait for DNS propagation (can take up to 48 hours, but usually minutes)
- Clear browser cache if needed

### Ingress Issues
- Check ingress status: `kubectl get ingress -n PROJECT-ENVIRONMENT`
- View ingress details: `kubectl describe ingress -n PROJECT-ENVIRONMENT`
- Check nginx logs: `kubectl logs -n ingress-nginx deployment/ingress-nginx-controller`

## Certificate Renewal

When your certificate expires:

1. Get new certificate files
2. Place them in `certs/` directory
3. Run update deployment with `--domain` parameter
4. The script will automatically update the Kubernetes secret

## Security Notes

- Never commit certificate files to git
- Keep private keys secure
- Use strong passwords for certificate generation
- Consider using cert-manager for automatic renewal in production 