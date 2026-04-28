from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import os, csv, time
from collections import Counter

# ── Settings ───────────────────────────
SITE_URL        = "https://legendary-mermaid-bfe60c.netlify.app"
SITE_PASSWORD   = "My-Drop-Site"
USERNAME        = "Admin"
PASSWORD        = "admin123"
OUTPUT_DIR      = "screenshots"
CSV_FILE        = "downgraded_users.csv"
DAYS_THRESHOLD  = 60
# ───────────────────────────────────────

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1400,900")
    prefs = {
        "download.default_directory": "/dev/null",
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "profile.default_content_setting_values.automatic_downloads": 2,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--disable-download-notification")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def take_screenshot(driver, name):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{name}.png")
    driver.save_screenshot(path)
    print(f"  📸 Screenshot saved → {path}")


def enter_site_password(driver, wait):
    print("\n[1] Entering Netlify site password...")
    driver.get(SITE_URL)
    pwd_field = wait.until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, "input[placeholder='Password']")))
    pwd_field.clear()
    pwd_field.send_keys(SITE_PASSWORD)
    wait.until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, "button.button"))).click()
    wait.until(EC.visibility_of_element_located(
        (By.ID, "login-screen")))
    take_screenshot(driver, "01_login_page")
    print("  ✅ Site password accepted!")


def login(driver, wait):
    print("\n[2] Logging into LicenseHub...")
    wait.until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR,
         "input[placeholder='Enter username']"))).clear()
    driver.find_element(
        By.CSS_SELECTOR,
        "input[placeholder='Enter username']").send_keys(USERNAME)
    wait.until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR,
         "input[placeholder='Enter password']"))).clear()
    driver.find_element(
        By.CSS_SELECTOR,
        "input[placeholder='Enter password']").send_keys(PASSWORD)
    driver.find_element(
        By.XPATH, "//button[text()='Sign In']").click()
    wait.until(EC.visibility_of_element_located(
        (By.ID, "app")))
    time.sleep(2)
    take_screenshot(driver, "02_logged_in")
    print("  ✅ Login successful!")


def go_to_license_manager(driver, wait):
    print("\n[3] Going to License Manager tab...")
    wait.until(EC.element_to_be_clickable((
        By.XPATH,
        "//*[contains(text(),'License Manager')]"))).click()
    wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "#lic-body tr")))
    time.sleep(2)
    take_screenshot(driver, "03_license_manager")
    print("  ✅ License Manager loaded!")


def force_close_modal(driver):
    try:
        driver.execute_script("""
            var modal = document.getElementById('modal-license');
            var bg = document.querySelector('.modal-bg');
            if (modal) modal.classList.remove('open');
            if (bg) bg.classList.remove('open');
        """)
        time.sleep(0.5)
    except:
        pass


def is_older_than_60_days(last_login_str):
    if not last_login_str.strip():
        return True, 9999
    try:
        last_login = datetime.strptime(
            last_login_str.strip(), "%b %d, %Y, %I:%M %p")
        days = (datetime.now() - last_login).days
        return days > DAYS_THRESHOLD, days
    except:
        return False, 0


def downgrade_user(driver, wait, username):
    """
    Fetches row fresh from #lic-body by username every time.
    Calls saveLicense() directly via JS.
    """
    try:
        force_close_modal(driver)
        time.sleep(0.5)

        # Fetch row fresh from License Manager table only
        fresh_row = None
        live_rows = driver.find_elements(
            By.CSS_SELECTOR, "#lic-body tr")

        for r in live_rows:
            try:
                cols = r.find_elements(By.TAG_NAME, "td")
                if len(cols) > 1 and \
                   cols[1].text.strip() == username:
                    fresh_row = r
                    break
            except:
                continue

        if not fresh_row:
            print(f"    ⚠️  Row not found for {username}")
            return False

        # Find Downgrade button
        btns = fresh_row.find_elements(By.TAG_NAME, "button")
        downgrade_btn = None
        for btn in btns:
            if btn.text.strip().lower() == "downgrade":
                downgrade_btn = btn
                break

        if not downgrade_btn:
            print(f"    ⏭️  No button — protected role")
            return False

        if not downgrade_btn.is_enabled():
            print(f"    🔒 Disabled — protected role")
            return False

        # Scroll and click
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            downgrade_btn)
        time.sleep(0.5)
        driver.execute_script(
            "arguments[0].click();", downgrade_btn)

        # Wait for modal
        wait.until(EC.visibility_of_element_located(
            (By.ID, "modal-license")))
        time.sleep(1)

        # Select Free
        select_el = wait.until(EC.element_to_be_clickable(
            (By.ID, "modal-lic-tier")))
        Select(select_el).select_by_visible_text("Free")
        time.sleep(0.5)

        # Call saveLicense() directly
        driver.execute_script("saveLicense();")

        # Wait for modal to close
        wait.until(EC.invisibility_of_element_located(
            (By.CSS_SELECTOR, ".modal-bg.open")))
        time.sleep(1.5)
        return True

    except Exception as e:
        print(f"    ❌ Failed: {e}")
        force_close_modal(driver)
        return False


def verify_downgrades(driver, wait, downgraded):
    """
    Reads the live site after all downgrades and confirms
    each user now shows FREE tier.
    """
    print("\n[5] Verifying downgrades on site...")
    time.sleep(2)

    # Reset to page 1
    driver.execute_script("licPage=1; renderLicTable();")
    time.sleep(1)

    usernames_to_check = {u["username"] for u in downgraded}
    verified   = []
    unverified = []

    while True:
        rows = driver.find_elements(
            By.CSS_SELECTOR, "#lic-body tr")

        for row in rows:
            try:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 5:
                    continue
                uname = cols[1].text.strip()
                tier  = cols[4].text.strip()

                if uname in usernames_to_check:
                    if "FREE" in tier.upper():
                        verified.append(uname)
                        print(f"  ✅ {uname:<20} → {tier}")
                    else:
                        unverified.append(uname)
                        print(f"  ❌ {uname:<20} → still {tier}!")
            except:
                continue

        try:
            next_btn = driver.find_element(By.ID, "lic-next")
            if not next_btn.is_enabled():
                break
            next_btn.click()
            time.sleep(1.5)
        except:
            break

    take_screenshot(driver, "05_verification")
    print(f"\n  Verified FREE  : {len(verified)}")
    print(f"  Not verified   : {len(unverified)}")
    return verified, unverified


def print_summary_table(downgraded, total_checked,
                        verified, unverified):
    W = 82

    def divider():
        print("+" + "─" * (W - 2) + "+")

    def section(title):
        divider()
        print("|  " + title.ljust(W - 4) + "|")

    def line(text):
        print("|  " + text.ljust(W - 4) + "|")

    def table_row(c1, c2, c3, c4, c5):
        print(f"| {str(c1):<16}| {str(c2):<22}| "
              f"{str(c3):<13}| {str(c4):<10}| {str(c5):<11}|")

    print("\n")
    section("DOWNGRADE SUMMARY REPORT")
    divider()
    table_row("Username", "Full Name",
              "From Tier", "To Tier", "Inactive")
    divider()

    if not downgraded:
        line("No users were downgraded.")
    else:
        for u in downgraded:
            verified_mark = "✅" \
                if u["username"] in verified else "⚠️"
            table_row(
                u["username"][:16],
                u["full_name"][:22],
                u["previous_tier"][:13],
                f"{u['new_tier']} {verified_mark}",
                u["days_inactive"][:11]
            )

    section("BREAKDOWN BY TIER")
    divider()
    tier_counts = Counter(
        u["previous_tier"] for u in downgraded)
    for tier, count in sorted(tier_counts.items()):
        line(f"{tier:<15} → Free   "
             f"× {count} user{'s' if count > 1 else ''}")

    section("FINAL COUNTS")
    divider()
    line(f"Total users checked    : {total_checked}")
    line(f"Total users downgraded : {len(downgraded)}")
    line(f"Total users skipped    : "
         f"{total_checked - len(downgraded)}")
    line(f"Verified FREE on site  : {len(verified)}")
    line(f"Not verified           : {len(unverified)}")
    line(f"Report saved to        : {CSV_FILE}")
    line(f"Completed at           : "
         f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    divider()
    print()


def process_all_pages(driver, wait):
    print(f"\n[4] Processing all pages...")
    print(f"    Downgrading inactive "
          f"{DAYS_THRESHOLD}+ days → Free")
    downgraded    = []
    total_checked = 0
    page_num      = 1
    already_seen  = set()

    while True:
        print(f"\n  --- Page {page_num} ---")
        time.sleep(2)

        rows = driver.find_elements(
            By.CSS_SELECTOR, "#lic-body tr")
        print(f"  Users on this page: {len(rows)}")

        # Get usernames on this page
        usernames_on_page = []
        for row in rows:
            try:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) > 1:
                    usernames_on_page.append(
                        cols[1].text.strip())
            except:
                continue

        # Stop if all users already processed
        if usernames_on_page and \
           all(u in already_seen for u in usernames_on_page):
            print("  ⚠️  All users already processed — stopping")
            break

        # Read full user data
        page_users = []
        for row in rows:
            try:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 6:
                    continue
                page_users.append({
                    "username":   cols[1].text.strip(),
                    "full_name":  cols[2].text.strip(),
                    "email":      cols[3].text.strip(),
                    "tier":       cols[4].text.strip(),
                    "role":       cols[5].text.strip(),
                    "last_login": cols[6].text.strip(),
                })
            except:
                continue

        # Process each user one by one
        for user in page_users:
            username   = user["username"]
            full_name  = user["full_name"]
            email      = user["email"]
            tier       = user["tier"]
            role       = user["role"]
            last_login = user["last_login"]

            # Skip if already processed
            if username in already_seen:
                continue

            already_seen.add(username)
            total_checked += 1

            # Skip already Free
            if tier.upper() == "FREE":
                print(f"  ⏭️  {username} — already Free")
                continue

            # Check inactivity
            inactive, days = is_older_than_60_days(last_login)
            if not inactive:
                print(f"  ⏭️  {username} — "
                      f"active ({days} days ago)")
                continue

            days_label = "Never logged in" \
                if days == 9999 else f"{days} days"

            print(f"  → Downgrading {username} "
                  f"({tier} | {days_label})...")

            success = downgrade_user(driver, wait, username)

            if success:
                print(f"    ✅ Done!")
                downgraded.append({
                    "username":      username,
                    "full_name":     full_name,
                    "email":         email,
                    "previous_tier": tier,
                    "new_tier":      "Free",
                    "role":          role,
                    "last_login":    last_login
                                     if last_login else "Never",
                    "days_inactive": days_label,
                    "actioned_at":   datetime.now().strftime(
                                     "%Y-%m-%d %H:%M:%S")
                })
            else:
                print(f"    ⏭️  Skipped (protected or failed)")

        # Move to next page
        try:
            next_btn = driver.find_element(By.ID, "lic-next")
            if not next_btn.is_enabled():
                print("\n  Last page reached.")
                break
            next_btn.click()
            page_num += 1
            time.sleep(2)
        except:
            print("\n  No more pages.")
            break

    take_screenshot(driver, "04_complete")
    return downgraded, total_checked


def save_to_csv(downgraded):
    print(f"\n  Saving report to {CSV_FILE}...")
    if not downgraded:
        print("  ⚠️  No users were downgraded")
        return
    exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=downgraded[0].keys())
        if not exists:
            writer.writeheader()
        writer.writerows(downgraded)
    print(f"  ✅ {len(downgraded)} records saved to {CSV_FILE}")


def main():
    print("=" * 50)
    print("  LicenseHub — Downgrade Inactive Users → Free")
    print("=" * 50)

    driver = setup_driver()
    wait   = WebDriverWait(driver, 15)

    try:
        enter_site_password(driver, wait)
        login(driver, wait)
        go_to_license_manager(driver, wait)
        downgraded, total_checked = process_all_pages(
            driver, wait)
        save_to_csv(downgraded)

        # Verify on live site
        verified, unverified = verify_downgrades(
            driver, wait, downgraded)

        # Print summary table
        print_summary_table(
            downgraded, total_checked,
            verified, unverified)

    except Exception as e:
        take_screenshot(driver, "ERROR")
        print(f"\n  ❌ Error: {e}")

    finally:
        print("  Browser staying open for 30 seconds...")
        print("  Check the site to verify downgrades!")
        time.sleep(30)
        driver.quit()


if __name__ == "__main__":
    main()