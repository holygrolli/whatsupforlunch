import scrapy


class LeosSpider(scrapy.Spider):
    name = "leos"
    allowed_domains = ["www.leosbrasserie.de"]
    start_urls = ['https://www.leosbrasserie.de/mittagsangebot-11-30-14-00/']

    def parse(self, response):
        for sel in response.xpath('//a[contains(@href,".png")]/@href'):
            link = sel.get()
            print(link)
            yield {"png":link}
