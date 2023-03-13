import requests
import datetime
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

bot = telegram.Bot(token="6016010541:AAFU3XJ8nWViXNcJpTg3Oyb7DhIs2242Fe4")

# 定义 CoinGecko API 的 URL
url = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin%2Cethereum&vs_currencies=usd'

# 定义获取价格的函数
def get_prices():
    # 发送 GET 请求获取价格数据
    response = requests.get(url)
    # 解析响应数据
    prices = response.json()
    # 获取 BTC 和 ETH 的价格
    btc_price = prices['bitcoin']['usd']
    eth_price = prices['ethereum']['usd']

    now = datetime.datetime.now()

    # 输出价格信息

    text = "🏷️ Spot Prices\n\n"
    text += f'<i>BTC price: ${btc_price:.2f}</i>\n<i>ETH price: ${eth_price:.2f}</i>\n\n'
    text += f'<i>{now.strftime("%Y-%m-%d %H:%M")}</i>'
    
    bot.send_message(chat_id="-922086924", text=text, parse_mode=telegram.ParseMode.HTML)

if __name__ == "__main__":
    get_prices()
