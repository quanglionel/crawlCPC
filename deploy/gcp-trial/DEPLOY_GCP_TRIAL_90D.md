# Google Cloud Trial 90 Days Deployment (Docker-only)

This guide deploys the crawler stack to a Google Cloud VM during trial credit period.

## Checklist

- [ ] Google Cloud trial account is active
- [ ] Ubuntu VM is created and has external IP
- [ ] Firewall allows `22`, `80`, `443`
- [ ] Domain A record points to VM external IP
- [ ] Project is cloned on VM
- [ ] Docker is installed and working
- [ ] `deploy/gcp-trial/.env.gcp-trial` is configured
- [ ] Services are up with `deploy_gcp_trial.sh`
- [ ] HTTPS works on your domain
- [ ] Migration plan before trial expiry is prepared

## 1) Create VM

Recommended baseline:

- OS: Ubuntu 22.04+
- Size: at least 1 vCPU / 1GB RAM (2GB RAM preferred)
- Disk: at least 16GB

On Google Cloud, add firewall tags or rules for:

- TCP 22 (SSH)
- TCP 80 (HTTP)
- TCP 443 (HTTPS)

## 2) Connect and clone project

```bash
ssh <your-user>@<your-vm-ip>
git clone <your-repo-url> crack
cd crack
```

## 3) Install Docker

```bash
sudo bash deploy/gcp-trial/scripts/install_docker_ubuntu.sh
newgrp docker
```

## 4) Configure environment

```bash
cp deploy/gcp-trial/.env.gcp-trial.example deploy/gcp-trial/.env.gcp-trial
```

Edit file `deploy/gcp-trial/.env.gcp-trial`:

- `DOMAIN`: your real domain
- `LETSENCRYPT_EMAIL`: your email

## 5) Deploy

```bash
bash deploy/gcp-trial/scripts/deploy_gcp_trial.sh
```

## 6) Verify

```bash
docker compose -f docker-compose.yml -f docker-compose.gcp-trial.yml ps
curl -I https://<your-domain>
```

## 7) Low-resource tuning (1GB RAM)

- Keep crawl workers low (1-2)
- Crawl in small batches
- Clean old output and logs regularly
- Avoid browser automation on this size

## 8) Migration before expiry (no downtime)

Do this 7-10 days before trial ends:

1. Provision target long-term VM (Oracle or paid VPS)
2. Copy data folders: `sources/`, `configs/`, `output/`
3. Deploy same compose stack on target VM
4. Switch DNS A record to new VM
5. Keep old VM online for 24 hours as rollback

## 9) Operations

Redeploy after updates:

```bash
git pull
bash deploy/gcp-trial/scripts/deploy_gcp_trial.sh
```

View logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.gcp-trial.yml logs -f web
docker compose -f docker-compose.yml -f docker-compose.gcp-trial.yml logs -f caddy
```
