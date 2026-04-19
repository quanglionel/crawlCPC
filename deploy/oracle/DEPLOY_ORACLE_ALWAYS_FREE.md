# Oracle Always Free Deployment (Docker-only)

This guide deploys the current crawler stack to an Oracle Cloud Always Free VM without service hibernation.

## Deployment checklist

- [ ] Oracle VM created (Ubuntu 22.04+, Always Free shape)
- [ ] Public IP is attached to VM
- [ ] Security rules open ports `22`, `80`, `443`
- [ ] Domain A record points to VM public IP
- [ ] Project cloned on VM
- [ ] Docker installed and working (`docker --version`)
- [ ] `deploy/oracle/.env.oracle` created and configured
- [ ] Services deployed with `deploy_oracle.sh`
- [ ] HTTPS works on your domain
- [ ] Backup plan enabled for `sources/`, `configs/`, `output/`
- [ ] (If crawling `khmertimes`) browser automation layer is planned (Playwright/proxy). Oracle deployment alone does not bypass Cloudflare challenge.

## 1) VM prerequisites

- Ubuntu 22.04+ VM (Always Free shape)
- Public IPv4 assigned
- Domain name pointing to this VM IP
- Open inbound ports in Oracle NSG/Security List: `22`, `80`, `443`

### Step 1 details (do this first)

1. Create VM

- In Oracle Cloud Console, create a Compute Instance.
- Image: Ubuntu 22.04 (or newer).
- Shape: Always Free eligible shape.
- Add your SSH public key while creating instance.

2. Confirm public IP

- In instance details, ensure a Public IPv4 is attached.
- Copy this IP for DNS step later.

3. Open required ports

- In VCN Security List (or NSG), add ingress rules:
	- TCP 22 (SSH)
	- TCP 80 (HTTP)
	- TCP 443 (HTTPS)
- Source CIDR can be `0.0.0.0/0` for web ports; for SSH prefer your own IP range if possible.

4. Verify from your local machine

```bash
ssh ubuntu@<your-vm-public-ip>
```

If SSH works, Step 1 is complete.

## 2) Upload project to the VM

```bash
git clone <your-repo-url> crack
cd crack
```

## 3) Install Docker

```bash
sudo bash deploy/oracle/scripts/install_docker_oracle.sh
# Re-login shell or run: newgrp docker
```

## 4) Configure environment

```bash
cp deploy/oracle/.env.oracle.example deploy/oracle/.env.oracle
```

Edit `deploy/oracle/.env.oracle`:

- `DOMAIN`: your real domain
- `LETSENCRYPT_EMAIL`: your email for Let's Encrypt

## 5) Deploy services

```bash
bash deploy/oracle/scripts/deploy_oracle.sh
```

This starts:

- `web` crawler UI/API service
- `caddy` reverse proxy with automatic HTTPS

## 6) Verify

```bash
docker compose -f docker-compose.yml -f docker-compose.oracle.yml ps
curl -I https://<your-domain>
```

Open in browser:

- `https://<your-domain>`

## 7) Basic operations

Update and redeploy:

```bash
git pull
bash deploy/oracle/scripts/deploy_oracle.sh
```

View logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.oracle.yml logs -f web
docker compose -f docker-compose.yml -f docker-compose.oracle.yml logs -f caddy
```

## 8) Notes

- This is the most practical free always-on option for this crawler workload.
- Keep `workers` conservative on Always Free resources.
- Back up `sources/`, `configs/`, and `output/` regularly.
