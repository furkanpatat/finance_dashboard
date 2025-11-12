import requests
import pandas as pd
from tqdm import tqdm
token = "d49l5n1r01qlaebhspa0d49l5n1r01qlaebhspag"  # <-- Buraya kendi Finnhub key'ini yaz
url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={token}"


print("📡 Finnhub'tan semboller çekiliyor...")
data = requests.get(url).json()
df = pd.DataFrame(data)

# Sadece Common Stock olanları al
df = df[df["type"] == "Common Stock"]
df = df[df["description"].notna() & (df["description"] != "")]

# Her sembolün geçerli olup olmadığını kontrol et
valid_symbols = []
for sym in tqdm(df["symbol"]):  # 500 tane kontrol et, istersen artır
    r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={sym}&token={token}")
    js = r.json()
    if js.get("c", 0) != 0:  # "c" (current price) sıfır değilse geçerli
        valid_symbols.append(sym)

clean_df = df[df["symbol"].isin(valid_symbols)][["symbol", "description"]]
clean_df.to_csv("us_list.csv", index=False, header=["Kod", "Ad"])

print(f"✅ Temiz us_list.csv oluşturuldu ({len(clean_df)} adet geçerli hisse).")


# CSV olarak kaydet
df[["symbol", "description"]].to_csv("us_list.csv", index=False, header=["Kod", "Ad"])

print(f"✅ Filtrelenmiş us_list.csv oluşturuldu. Toplam {len(df)} sembol kaldı.")
