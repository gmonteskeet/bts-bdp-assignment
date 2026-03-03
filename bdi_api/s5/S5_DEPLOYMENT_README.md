# S5 Deployment Guide: FastAPI + PostgreSQL on AWS

## Architecture Overview

```
┌─────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   Browser   │ ──────► │   EC2 Instance  │ ──────► │  RDS PostgreSQL │
│             │  :8080  │   (FastAPI)     │  :5432  │   (hr_database) │
└─────────────┘         └─────────────────┘         └─────────────────┘
```

## Prerequisites

- AWS Account
- RDS PostgreSQL instance (can be stopped to save costs)
- SSH key pair for EC2

---

## Step 1: Set Up RDS PostgreSQL

### 1.1 Start your RDS instance (if stopped)
- AWS Console → RDS → Databases
- Select your instance → Actions → **Start**
- Wait 5-10 minutes for it to become available

### 1.2 Get your RDS endpoint
- Click on your database instance
- Copy the **Endpoint** (e.g., `my-db.abc123.us-east-1.rds.amazonaws.com`)

### 1.3 Create the hr_database
Connect to RDS from your local machine (or EC2):

```bash
psql -h YOUR_RDS_ENDPOINT -U postgres -p 5432
```

Then create the database:

```sql
CREATE DATABASE hr_database;
\q
```

### 1.4 Configure RDS Security Group
- Go to your RDS instance → Security → VPC security groups
- Edit inbound rules
- Add rule: **PostgreSQL (5432)** from your EC2 security group (or 0.0.0.0/0 for testing)

---

## Step 2: Launch EC2 Instance

### 2.1 Create EC2 instance
- AWS Console → EC2 → Launch Instance
- **AMI:** Amazon Linux 2023 or Ubuntu 22.04
- **Instance type:** t2.micro (free tier)
- **Key pair:** Select or create one
- **Network settings:** Allow SSH (22) and Custom TCP (8080)

### 2.2 Configure Security Group
Inbound rules:
| Type       | Port | Source    |
|------------|------|-----------|
| SSH        | 22   | Your IP   |
| Custom TCP | 8080 | 0.0.0.0/0 |

---

## Step 3: Deploy FastAPI on EC2

### 3.1 SSH into EC2

```bash
ssh -i your-key.pem ec2-user@YOUR_EC2_PUBLIC_IP
```

### 3.2 Install dependencies

**Amazon Linux:**
```bash
sudo yum update -y
sudo yum install python3.11 python3.11-pip git -y
```

**Ubuntu:**
```bash
sudo apt update
sudo apt install python3.11 python3.11-pip git -y
```

### 3.3 Clone repository

```bash
git clone https://github.com/YOUR_USERNAME/bts-bdp-assignment.git
cd bts-bdp-assignment
```

### 3.4 Install Python packages

```bash
pip3 install -r requirements.txt
```

### 3.5 Set database connection

```bash
export BDI_DB_URL="postgresql://postgres:YOUR_PASSWORD@YOUR_RDS_ENDPOINT:5432/hr_database?sslmode=require"
```

Replace:
- `YOUR_PASSWORD` — your RDS master password
- `YOUR_RDS_ENDPOINT` — e.g., `my-db.abc123.us-east-1.rds.amazonaws.com`

### 3.6 Run the API

```bash
uvicorn bdi_api.app:app --host 0.0.0.0 --port 8080
```

---

## Step 4: Test the Deployment

### 4.1 Access the API docs
Open in browser:
```
http://YOUR_EC2_PUBLIC_IP:8080/docs
```

### 4.2 Initialize the database
In the Swagger UI (`/docs`):
1. Execute `POST /api/s5/db/init` — creates tables
2. Execute `POST /api/s5/db/seed` — populates sample data
3. Test `GET /api/s5/departments/` — should return 5 departments

---

## Troubleshooting

### Cannot connect to RDS from EC2
- Check RDS security group allows inbound from EC2's security group on port 5432
- Verify RDS is in "Available" state
- Test connection: `psql -h YOUR_RDS_ENDPOINT -U postgres -p 5432`

### Port 8080 not accessible
- Check EC2 security group allows inbound on port 8080
- Make sure uvicorn is running with `--host 0.0.0.0`

### Module not found errors
- Ensure you're in the project directory
- Run `pip3 install -r requirements.txt`

---

## Cost Management

| Service | Estimated Cost | How to Stop |
|---------|---------------|-------------|
| EC2 t2.micro | ~$8/month (or free tier) | Stop instance |
| RDS db.t3.micro | ~$12-15/month | Stop temporarily (auto-restarts after 7 days) |
| Data transfer | Minimal | N/A |

**To minimize costs:**
- Stop EC2 when not using
- Stop RDS (remember it auto-restarts after 7 days)
- Delete resources after assignment is graded
