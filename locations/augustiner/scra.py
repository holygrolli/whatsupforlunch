import sys
import scrapy


class LunchSpider(scrapy.Spider):
    name = "LunchSpider"
    allowed_domains = ["www.augustiner-leipzig.de"]
    start_urls = ['https://www.augustiner-leipzig.de/speisen/']

    def parse(self, response):
        links = response.xpath('//a[contains(@href,"pdf") and contains(@href,"Mittag")]/@href')
        if (len(links) > 0):
            for sel in links:
                link = sel.get()
                print(link)
                yield {"pdf":link}
        else:
            sys.exit(1)
