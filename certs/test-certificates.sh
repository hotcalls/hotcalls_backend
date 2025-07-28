#!/bin/bash

# Test SSL/TLS certificates for deployment

echo "SSL/TLS Certificate Test"
echo "========================"

# Check if files exist
if [[ ! -f "tls.cer" ]]; then
    echo "❌ ERROR: tls.cer not found"
    exit 1
fi

if [[ ! -f "private.key" ]]; then
    echo "❌ ERROR: private.key not found"
    exit 1
fi

echo "✅ Certificate files found"

# Check certificate details
echo ""
echo "Certificate Information:"
echo "-----------------------"
openssl x509 -in tls.cer -noout -subject -issuer -dates

# Check if private key matches certificate
echo ""
echo "Checking if private key matches certificate..."
CERT_MODULUS=$(openssl x509 -noout -modulus -in tls.cer | openssl md5)
KEY_MODULUS=$(openssl rsa -noout -modulus -in private.key | openssl md5)

if [[ "$CERT_MODULUS" == "$KEY_MODULUS" ]]; then
    echo "✅ Private key matches certificate"
else
    echo "❌ ERROR: Private key does not match certificate"
    exit 1
fi

# Check certificate chain
echo ""
echo "Certificate Chain:"
echo "-----------------"
openssl crl2pkcs7 -nocrl -certfile tls.cer | openssl pkcs7 -print_certs -noout

echo ""
echo "✅ Certificate validation passed!" 