#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess


def load_env_file(env_file):
    if not os.path.exists(env_file):
        print(f"Warning: {env_file} not found, using defaults")
        return
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value


def main():
    parser = argparse.ArgumentParser(description='Deploy MCP Server')
    parser.add_argument('--host', default=None)
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--transport', choices=['stdio', 'streamable-http'], default=None)
    parser.add_argument('--env-file', default='.env.deployment')
    parser.add_argument('--dev', action='store_true')

    args = parser.parse_args()

    load_env_file(args.env_file)

    if args.host:
        os.environ['MCP_HOST'] = args.host
    if args.port:
        os.environ['MCP_PORT'] = str(args.port)
    if args.transport:
        os.environ['MCP_TRANSPORT'] = args.transport
    if args.dev:
        os.environ['MCP_TRANSPORT'] = 'stdio'

    host = os.environ.get('MCP_HOST', '0.0.0.0')
    port = os.environ.get('MCP_PORT', '8000')
    transport = os.environ.get('MCP_TRANSPORT', 'streamable-http')

    print("Deploying MCP Server:")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Transport: {transport}")
    print(f"  API Base URL: {os.environ.get('API_BASE_URL', 'http://localhost:8000')}")
    print()

    try:
        subprocess.run([sys.executable, 'server.py'], check=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"Error running server: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())



