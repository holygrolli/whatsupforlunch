import sys
import scrapy


class LeosSpider(scrapy.Spider):
    name = "leos"
    allowed_domains = ["www.leosbrasserie.de"]
    start_urls = ['https://www.leosbrasserie.de/mittagsangebot-11-30-14-00/']

    def parse(self, response):
        links = response.xpath('//a[contains(@href,".png") or contains(@href,".jpg")]/@href')
        if (len(links) > 0):
            for sel in links:
                link = sel.get()
                print(link)
                yield {"png":link}
        else:
            sys.exit(1)
