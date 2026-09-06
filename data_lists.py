"""Static lists — currencies, regions, languages."""

# (code, display name) — rates Admin Panel > Settings > Currency Rates se badalte hain
CURRENCIES = [
    ("USDT", "USDT"),
    ("USD", "United States Dollar"),
    ("PKR", "Pakistani Rupee"),
    ("INR", "Indian Rupee"),
    ("BDT", "Bangladeshi Taka"),
    ("AED", "UAE Dirham"),
    ("SAR", "Saudi Riyal"),
    ("TRY", "Turkish Lira"),
    ("RUB", "Russian Ruble"),
    ("IDR", "Indonesian Rupiah"),
    ("BRL", "Brazilian Real"),
    ("EGP", "Egyptian Pound"),
    ("NGN", "Nigerian Naira"),
    ("UZS", "Uzbekistani Som"),
    ("UAH", "Ukrainian Hryvnia"),
    ("VND", "Vietnamese Dong"),
    ("EUR", "Euro"),
]

REGIONS = [
    "India", "Russia", "Indonesia", "United States", "Brazil", "Iran",
    "Uzbekistan", "Egypt", "Pakistan", "Bangladesh", "Turkey", "Ukraine",
    "Nigeria", "Vietnam", "Saudi Arabia", "UAE", "United Kingdom", "Germany",
    "France", "Spain", "Italy", "Netherlands", "Poland", "Mexico",
    "Argentina", "Colombia", "Philippines", "Malaysia", "Thailand", "Nepal",
    "Sri Lanka", "Afghanistan", "Iraq", "Morocco", "Algeria", "Kazakhstan",
]

LANGUAGES = [
    ("EN", "🇬🇧 English"),
    ("AR", "🇸🇦 العربية"),
    ("VI", "🇻🇳 Tiếng Việt"),
    ("HI", "🇮🇳 हिन्दी"),
    ("BN", "🇧🇩 বাংলা"),
    ("UR", "🇵🇰 اردو"),
    ("RU", "🇷🇺 Русский"),
    ("TR", "🇹🇷 Türkçe"),
]

METHOD_NAMES = {
    "binance": "🟡 Binance Pay",
    "bep20": "🪙 USDT BEP20",
    "bybit": "⚫ Bybit Pay",
    "ton": "💎 USDT TON",
    "ltc": "🩶 LTC",
    "crypto": "🤖 Crypto Bot",
    "others": "🌐 Others",
}
