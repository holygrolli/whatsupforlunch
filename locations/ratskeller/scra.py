import sys
import scrapy


class RatskellerSpider(scrapy.Spider):
    name = "ratskeller"
    allowed_domains = ["ratskeller.restaurant"]
    start_urls = ['https://ratskeller.restaurant/kantine-leipzig/speiseplan/']

    def parse(self, response):
        links = response.xpath('//section[.//a[contains(@href,"pdf")]][1]//a[contains(@href,"pdf")]/@href')
        if (len(links) > 0):
            for sel in links:
                link = sel.get()
                print(link)
                yield {"pdf":link}
        else:
            sys.exit(1)
