import sys
import json
import os
import time
import base64
from pathlib import Path
from odoo_client import OdooClient

def configure_stdout_utf8():
    """Ensure standard output and error streams use UTF-8 encoding."""
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        os.environ['PYTHONIOENCODING'] = 'utf-8'

def load_existing_backup(path):
    """Load existing employee backup from JSON file. Returns dict keyed by email."""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {emp['work_email']: emp for emp in data if emp.get('work_email')}
    return {}

def save_backup(path, data_dict):
    """Save the backup data as a list of employees to a JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(list(data_dict.values()), f, indent=4, ensure_ascii=False)

def build_employee_dict(emp, image_dir):
    """Extract and structure employee data into a clean dictionary for backup."""
    dept_name = emp['department_id'][1] if emp.get('department_id') else ''
    email = emp.get('work_email', '')
    if not email:
        return None  # Skip employees without email

    username = email.split('@')[0]
    image_path = os.path.join(image_dir, f"{username}.png").replace('\\', '/')

    # Extract linked fields' display names
    manager = emp['parent_id'][1] if emp.get('parent_id') else ''
    coach = emp['coach_id'][1] if emp.get('coach_id') else ''
    company = emp['company_id'][1] if emp.get('company_id') else ''

    return {
        'name': emp.get('name', ''),
        'work_email': email,
        'work_phone': emp.get('work_phone', ''),
        'job_title': emp.get('job_title', ''),
        'department_name': dept_name,
        'photo_name': f"{username}.png",

        # Extended fields
        'manager': manager,
        'mentor': coach,
        'company': company,
    }

def get_timestamp():
    """Return current timestamp string."""
    return time.strftime("%Y-%m-%d %H:%M:%S")

def sync_employee_images(current_by_email, existing_by_email, image_dir):
    """
    Save or update employee images based on photo base64 content.
    Also removes images for deleted employees.
    """
    os.makedirs(image_dir, exist_ok=True)

    current_emails = set(current_by_email.keys())
    existing_emails = set(existing_by_email.keys())

    for email, data in current_by_email.items():
        username = email.split('@')[0]
        img_filename = f"{username}.png"
        img_path = os.path.join(image_dir, img_filename)
        new_b64 = data.get('photo_b64', '')

        if not new_b64:
            continue  # No image to process

        if os.path.exists(img_path):
            try:
                # Compare base64 content before writing
                with open(img_path, 'rb') as img_file:
                    existing_img_data = base64.b64encode(img_file.read()).decode('utf-8')
                if existing_img_data == new_b64:
                    continue  # No change in image
                else:
                    with open(img_path, 'wb') as img_file:
                        img_file.write(base64.b64decode(new_b64))
                    print(f"{get_timestamp()} - Image updated for employee {email}")
            except Exception as e:
                print(f"{get_timestamp()} - Warning: Could not verify image for {email}, will overwrite: {e}")
        else:
            try:
                # Save new image
                with open(img_path, 'wb') as img_file:
                    img_file.write(base64.b64decode(new_b64))
                print(f"{get_timestamp()} - Image updated for employee {email}")
            except Exception as e:
                print(f"{get_timestamp()} - Error saving image for {email}: {e}")

        # Clean up base64 key before saving
        data['photo_name'] = img_filename
        if 'photo_b64' in data:
            del data['photo_b64']

    # Delete images for employees no longer present
    removed_emails = existing_emails - current_emails
    for email in removed_emails:
        username = email.split('@')[0]
        img_path = os.path.join(image_dir, f"{username}.png")
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
                print(f"{get_timestamp()} - Removed image for deleted employee {email}")
            except Exception as e:
                print(f"{get_timestamp()} - Error deleting image for {email}: {e}")

def fetch_odoo_employees(client, image_dir):
    """
    Fetch employee records from Odoo with extended fields.
    Attach base64 photo data temporarily for comparison.
    """
    current_ids = client.search_all_employees()
    fields = [
        'name', 'work_email', 'work_phone', 'job_title', 'image_1920',
        'department_id', 'parent_id', 'coach_id', 'company_id'
    ]
    current_data = client.read_employees_in_batches(current_ids, fields)

    new_backup = {}
    for emp in current_data:
        email = emp.get('work_email', '')
        if not email:
            continue
        emp_dict = build_employee_dict(emp, image_dir)
        if emp_dict is None:
            continue
        emp_dict['photo_b64'] = emp.get('image_1920', '')  # temp key for comparison
        new_backup[email] = emp_dict

    return new_backup

def main():
    configure_stdout_utf8()
    client = OdooClient()
    print(f"Authenticated with Odoo (UID: {client.uid})")


    json_path = '../hr_backup.json'
    image_dir = '../emp_img'
    
    print(f"{get_timestamp()} - Loading existing backup file: backup-bb-spain.json")
    existing_by_email = load_existing_backup(json_path)

    print(f"{get_timestamp()} - Fetching employees data from Odoo...")
    new_backup = fetch_odoo_employees(client, image_dir)

    existing_emails = set(existing_by_email.keys())
    new_emails = set(new_backup.keys())

    delta_backup = {}
    changes_found = False

    # Detect removed employees
    removed_emails = existing_emails - new_emails
    for email in removed_emails:
        changes_found = True
        print(f"{get_timestamp()} - Employee removed: {email}")

    # Detect added employees
    added_emails = new_emails - existing_emails
    for email in added_emails:
        changes_found = True
        print(f"{get_timestamp()} - Employee added: {email}")
        delta_backup[email] = new_backup[email]

    # Detect updated employees (data or image)
    for email in new_emails & existing_emails:
        old_emp = existing_by_email[email].copy()
        new_emp = new_backup[email].copy()

        # Exclude base64 before comparing dictionaries
        old_emp.pop('photo_b64', None)
        new_emp.pop('photo_b64', None)

        data_changed = (old_emp != new_emp)
        if data_changed:
            changes_found = True
            print(f"{get_timestamp()} - Employee updated: {email} (data updated)")
            delta_backup[email] = new_backup[email]
        else:
            delta_backup[email] = new_backup[email]

    if changes_found:
        # Sync images only for changed or new employees
        sync_employee_images(delta_backup, existing_by_email, image_dir)

        # Clean up temporary base64 before saving
        for emp in delta_backup.values():
            emp.pop('photo_b64', None)

        print(f"{get_timestamp()} - Saving backup file...")
        save_backup(json_path, delta_backup)
        print(f"{get_timestamp()} - Backup saved successfully with {len(delta_backup)} changed employees.")
    else:
        print(f"{get_timestamp()} - No changes detected compared to existing backup. Backup not updated.")

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
