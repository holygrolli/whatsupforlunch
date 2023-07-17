import sys
import scrapy


class Lecasino(scrapy.Spider):
    name = "lecasino"
    allowed_domains = ["www.l.de"]
    start_urls = ['https://www.l.de/gruppe/das-sind-wir/leipziger-gruppe/leipziger-servicebetriebe-lsb-gmbh/le-casino/']

    def parse(self, response):
        links = response.xpath('//a[contains(@href,"pdf") and contains(@href,"Speiseplan")]/@href')
        if (len(links) > 0):
            for sel in links:
                link = sel.get()
                print(link)
                yield {"pdf":link}
        else:
            sys.exit(1)
