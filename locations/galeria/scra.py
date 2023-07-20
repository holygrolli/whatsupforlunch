import scrapy


class GaleriaSpider(scrapy.Spider):
    name = "galeria"
    allowed_domains = ["galeria-restaurant.de/"]
    start_urls = ['https://galeria-restaurant.de/fillialen-galeria-restaurant-leipzig/']

    def parse(self, response):
        for sel in response.xpath('//a[contains(@href,"pdf")]/@href'):
            link = sel.get()
            print(link)
            yield {"pdf":link}
