import asyncio
from datetime import datetime, timedelta
import logging
import platform


import aiohttp
import websockets
import names
from websockets import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK
from aiofile import async_open
from aiopath import AsyncPath

aiohttp_session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))

logging.basicConfig(level=logging.INFO)
log_file_path = "exchange_logs.txt"
apath = AsyncPath("exchange_logs.txt")

#функция логирования в файл
async def log_to_file(log_message):
    if await apath.exists():
        async with async_open(apath, "a") as log_file:
            await log_file.write(f"{datetime.now().isoformat()} - {log_message}\n")
    else:
        async with async_open(apath, "w") as log_file:
            await log_file.write(f"{datetime.now().isoformat()} - {log_message}\n")

#функция получения json данных за конкретную дату 
async def fetch_data(session, date):
    url = f"https://api.privatbank.ua/p24api/exchange_rates?json&date={date}"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                print(f"Error status: {response.status} for {url}")
    except aiohttp.ClientConnectorError as err:
                print(f'Connection error: {url}', str(err))


# функция обработки данных по курсам EUR и USD
async def get_exchange(response):
    exchange_euro, *_ = list(filter(lambda el: el['currency'] == 'EUR', response['exchangeRate']))
    exchange_usd, *_= list(filter(lambda el: el['currency'] == 'USD', response['exchangeRate']))
    data = f"{response['date']}: 'EUR': 'sale': {exchange_euro['saleRate']}, 'purchase': {exchange_euro['purchaseRate']},'USD': 'sale': {exchange_usd['saleRate']}, 'purchase': {exchange_usd['purchaseRate']}" 
    return  data


#функция выполнения запросов
async def request(current_day=0):
    results = []
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:   
        tasks = [] 
        for day  in range(0, int(current_day + 1)):
            date = datetime.now() - timedelta(days=day)
            formatted_date = date.strftime("%d.%m.%Y")
            tasks.append(fetch_data(session, formatted_date))
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for response in responses:
            try:
                data = await get_exchange(response)
                results.append(data)
            except TypeError:
                        pass
    return f"{'| '.join(results)}\n"


#реализация чата на веб-сокетах
class Server:
    clients = set()

    async def register(self, ws: WebSocketServerProtocol):
        ws.name = names.get_full_name()
        self.clients.add(ws)
        logging.info(f'{ws.remote_address} connects')

    async def unregister(self, ws: WebSocketServerProtocol):
        self.clients.remove(ws)
        logging.info(f'{ws.remote_address} disconnects')

    async def send_to_clients(self, message: str):
        if self.clients:
            [await client.send(message) for client in self.clients]

    async def send_to_client(self, message: str, ws: WebSocketServerProtocol ):
        await ws.send(message)

    async def ws_handler(self, ws: WebSocketServerProtocol):
        await self.register(ws)
        try:
            await self.distrubute(ws)
        except ConnectionClosedOK:
            pass
        finally:
            await self.unregister(ws)

    async def distrubute(self, ws: WebSocketServerProtocol):
        async for message in ws:
            if message.startswith('exchange'):
                exc = message.split()
                if len(exc) > 1:
                    r = await request(int(exc[1]))
                    await self.send_to_client(r, ws)
                    log_message = f"{ws.name} used 'exchange'"
                    await log_to_file(log_message)
                else:
                    r = await request()
                    await self.send_to_client(r, ws) 
                    log_message = f"{ws.name} used 'exchange'"
                    await log_to_file(log_message)
                                      
            else: 
                await self.send_to_clients(f"{ws.name}: {message}")


async def main():
    server = Server()
    async with websockets.serve(server.ws_handler, 'localhost', 8080):
        await asyncio.Future()  # run forever

if __name__ == '__main__':
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
