"""
Script to backup database to cloud storage
"""
import os
import json
import csv
import boto3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def backup_to_s3():
    """Backup database files to AWS S3 (free tier)"""
    try:
        # AWS S3 configuration (free tier)
        s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID', ''),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY', ''),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        
        bucket_name = os.getenv('S3_BUCKET_NAME', 'fam-api-database')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Backup JSON
        if os.path.exists('fam_database.json'):
            s3_key = f'backups/fam_database_{timestamp}.json'
            s3.upload_file('fam_database.json', bucket_name, s3_key)
            print(f"✅ JSON backed up to S3: {s3_key}")
        
        # Backup CSV
        if os.path.exists('fam_database.csv'):
            s3_key = f'backups/fam_database_{timestamp}.csv'
            s3.upload_file('fam_database.csv', bucket_name, s3_key)
            print(f"✅ CSV backed up to S3: {s3_key}")
        
        return True
        
    except Exception as e:
        print(f"❌ S3 backup error: {e}")
        return False

def backup_to_github():
    """Backup to GitHub repository"""
    try:
        import git
        
        repo_path = './database_backup'
        
        if not os.path.exists(repo_path):
            repo_url = os.getenv('GITHUB_REPO_URL', '')
            if repo_url:
                repo = git.Repo.clone_from(repo_url, repo_path)
            else:
                print("⚠️ GitHub repo URL not configured")
                return False
        else:
            repo = git.Repo(repo_path)
        
        # Copy database files
        import shutil
        if os.path.exists('fam_database.json'):
            shutil.copy2('fam_database.json', f'{repo_path}/fam_database.json')
        if os.path.exists('fam_database.csv'):
            shutil.copy2('fam_database.csv', f'{repo_path}/fam_database.csv')
        
        # Commit and push
        repo.git.add('.')
        repo.index.commit(f'Database backup {datetime.now().isoformat()}')
        origin = repo.remote(name='origin')
        origin.push()
        
        print("✅ Database backed up to GitHub")
        return True
        
    except Exception as e:
        print(f"❌ GitHub backup error: {e}")
        return False

if __name__ == "__main__":
    print("💾 Starting database backup...")
    
    # Try S3 backup first
    if backup_to_s3():
        print("🎉 S3 backup successful")
    
    # Try GitHub backup
    if backup_to_github():
        print("🎉 GitHub backup successful")
    
    print("✅ Backup process completed")
