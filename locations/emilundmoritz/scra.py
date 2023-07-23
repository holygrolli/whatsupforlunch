import sys
import scrapy
import lxml.html.clean as clean
from htmlmin import minify

safe_attrs = set(['src', 'alt', 'href', 'title'])
kill_tags = ['object', 'iframe']
cleaner = clean.Cleaner(safe_attrs_only=True, safe_attrs=safe_attrs, kill_tags=kill_tags)

class Spider(scrapy.Spider):
    name = "Spider"
    allowed_domains = ["emil-und-moritz.de"]
    start_urls = ['https://emil-und-moritz.de/']

    def parse(self, response):
        mittagsangebot = response.xpath('//div[contains(@class,"section_title") and descendant::text()[contains(.,"Woche")]]')
        if (len(mittagsangebot) == 1):
            for sel in mittagsangebot:
                div = sel.get()
                cleaned_html = minify(cleaner.clean_html(div))
                print(cleaned_html)
                yield {"div":cleaned_html}
        else:
            sys.exit(1)
