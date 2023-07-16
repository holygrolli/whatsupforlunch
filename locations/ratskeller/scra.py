import scrapy


class RatskellerSpider(scrapy.Spider):
    name = "ratskeller"
    allowed_domains = ["ratskeller.restaurant"]
    start_urls = ['https://ratskeller.restaurant/kantine-leipzig/speiseplan/']

    def parse(self, response):
        for sel in response.xpath('//section[.//a[contains(@href,"pdf")]][1]//a[contains(@href,"pdf")]/@href'):
            link = sel.get()
            print(link)
            yield {"pdf":link}
