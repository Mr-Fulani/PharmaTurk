import asyncio
from bs4 import BeautifulSoup
import httpx

async def fetch_test():
    url = "https://ilacfiyati.com/ilaclar?pg=1"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        print(f"Status: {response.status_code}")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.select('a[href*="/ilaclar/"]')
        print(f"Found {len(links)} links")
        for link in links[:3]:
            print(link.get('href'))

if __name__ == "__main__":
    asyncio.run(fetch_test())
