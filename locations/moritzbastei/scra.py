import sys
import scrapy
import lxml.html.clean as clean

safe_attrs = set(['src', 'alt', 'href', 'title', 'width', 'height'])
kill_tags = ['object', 'iframe']
cleaner = clean.Cleaner(safe_attrs_only=True, safe_attrs=safe_attrs, kill_tags=kill_tags)

class MBSpider(scrapy.Spider):
    name = "MB"
    allowed_domains = ["www.moritzbastei.de"]
    start_urls = ['https://www.moritzbastei.de/gastronomie-kneipe-bistro-drinks/']

    def parse(self, response):
        mittagsangebot = response.xpath('//div[contains(@class,"foodMenu--weekly")]/parent::*')
        if (len(mittagsangebot) == 1):
            for sel in mittagsangebot:
                div = sel.get()
                cleaned_html = cleaner.clean_html(div)
                print(cleaned_html)
                yield {"div":cleaned_html}
        else:
            sys.exit(1)
