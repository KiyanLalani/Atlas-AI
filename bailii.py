import os
import asyncio
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from steel import Steel
from dotenv import load_dotenv

load_dotenv()

class BailiiScraper:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Initialize Steel client
        self.client = Steel(
            steel_api_key=os.getenv('STEEL_API_KEY'),
        )
        # Load API token from environment variables
        self.api_token = os.getenv('URLTOTEXT_API_TOKEN')

    async def scrape_page_content(self, url):
        """Scrape content from a specific page using the new scraper API."""
        try:
            api_url = 'https://urltotext.com/api/v1/urltotext/'
            headers = {
                'Authorization': f'Token {self.api_token}',
                'Content-Type': 'application/json'
            }
            data = {
                'url': url,
                'output_format': 'text',
                'extract_main_content': False,
                'render_javascript': False,
                'residential_proxy': False
            }
            response = requests.post(api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == requests.codes.ok:
                content = response.json().get('data', {}).get('content', '')
                # Remove newlines from the content
                content = content.replace('\n', ' ')
                return content
            else:
                return f"Error: {response.status_code}, {response.text}"
        except Exception as e:
            return str(e)

    async def run_scraper(self, search_query):
        # Create a Steel session with additional features
        session = self.client.sessions.create(
            use_proxy=False,
            solve_captcha=False,
        )
        
        collected_links = []
        scraped_contents = [] # Initialize list to store scraped content
        
        try:
            # Start Playwright and connect to Steel
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(
                    f'wss://connect.steel.dev?apiKey={os.getenv("STEEL_API_KEY")}&sessionId={session.id}'
                )
                
                # Create page at existing context to ensure session is recorded
                context = browser.contexts[0]
                page = await context.new_page()
                
                # Navigate to BAILII
                await page.goto("https://www.bailii.org/")
                await page.get_by_role("textbox").click()
                await page.get_by_role("textbox").fill(search_query)
                await page.get_by_role("button", name="Search").click()
                
                # Wait for the results to load
                await page.wait_for_load_state("networkidle")
                
                # Find all links within the ordered list with params start="1" and filter out unwanted content
                links = await page.evaluate('''() => {
                    const ol = document.querySelector('ol[start="1"]');
                    if (!ol) return [];
                    
                    const linkElements = ol.querySelectorAll('a');
                    return Array.from(linkElements)
                        .filter(link => !link.textContent.includes('View without highlighting'))
                        .map(link => ({
                            text: link.textContent.trim(),
                            url: link.href
                        }));
                }''')
                
                # Limit to top 3 links
                collected_links = links[:3]
                
                # Clean up Playwright resources
                await context.close()
                await browser.close()
        
        finally:
            # Always release the Steel session
            self.client.sessions.release(session.id)
        
        # Now use the API to scrape detailed content from each link
        if collected_links:
            print("\nStarting detailed content scraping with API...")
            
            # Process links with the API
            for i, link in enumerate(collected_links, 1):
                print(f"Scraping {i}/{len(collected_links)}: {link['text'][:40]}...")
                result = await self.scrape_page_content(link['url'])
                print(f"Content from {link['url']}:\n{result}\n")
                scraped_contents.append(result) # Store scraped content
                # Small delay to avoid overwhelming the server
                await asyncio.sleep(1)
                
        return scraped_contents # Return the list of scraped contents

# Example usage:
# scraper = BailiiScraper()
# asyncio.run(scraper.run_scraper("uk offenders on drug supply at festivals"))