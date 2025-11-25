import scrapy
import os
from pathlib import Path
import lxml.html as lxml_html

class Lecasino(scrapy.Spider):
    name = "lecasino"
    allowed_domains = ["www.l.de"]
    start_urls = ['https://www.l.de/gruppe/das-sind-wir/leipziger-gruppe/leipziger-servicebetriebe-lsb-gmbh/le-casino/']

    # storage for fetched menu pages' HTML
    menu_pages_html = None
    # base directory to save fetched HTML pages
    artifacts_dir = Path(__file__).resolve().parents[2] / 'tmp'

    def parse(self, response):
        print(response.body)
        links = response.xpath('//a[contains(text(),"Speiseplan")]/@href')
        if (len(links) > 0):
            # initialize storage for this crawl
            self.menu_pages_html = []
            for sel in links:
                link = sel.get()
                full = link if link.startswith('http') else "https://www.l.de" + link
                print(full)
                # schedule a request to fetch the menu page and process it
                yield scrapy.Request(url=full, callback=self.parse_menu_page, cb_kwargs={"source_url": full})
        else:
            from scrapy.exceptions import CloseSpider
            raise CloseSpider('no_speiseplan_links')

    def parse_menu_page(self, response, source_url=None):
        # store the raw HTML of the menu page to disk
        html = response.text
        # ensure artifacts directory exists
        try:
            os.makedirs(self.artifacts_dir, exist_ok=True)
        except Exception:
            pass

        # generate a safe filename from the URL
        name = source_url.replace('://', '_').replace('/', '_')
        filename = f"lecasino_{name}.html"
        full_path = str(self.artifacts_dir / filename)

        # write file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(html)

        # keep a small in-memory index of saved files (optional)
        if self.menu_pages_html is None:
            self.menu_pages_html = []
        self.menu_pages_html.append(full_path)

        # yield the saved file path so downstream processing can use it
        # Attempt to extract the Speiseplan content and save a cleaned HTML
        try:
            # look for the heading that contains "Speiseplan" (German)
            # and capture the nearest parent container that holds the plan
            heading_sel = response.xpath("//h2[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'speiseplan')]")
            cleaned_html = None
            if heading_sel:
                h2 = heading_sel.get()
                # try to get the ancestor container that likely wraps the plan
                container = heading_sel.xpath("ancestor::div[contains(@class,'group/container')][1]")
                if not container or len(container) == 0:
                    # fallback: take the parent section of the h2
                    container = heading_sel.xpath('..')
                if container and len(container) > 0:
                    inner = container.get()
                    # build a minimal HTML document
                    cleaned_html = (
                        '<!doctype html>'
                        '<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                        f'<title>{response.xpath("//title/text()").get(default="Speiseplan")}</title>'
                        '</head><body>' + inner + '</body></html>'
                    )
            # If we couldn't find via h2, attempt to find the block by searching for the weekday headings
            if not cleaned_html:
                weekdays = ['montag','dienstag','mittwoch','donnerstag','freitag']
                # xpath: any element that contains one of the weekday names as a full word
                weekday_expr = ' or '.join([f"contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{w}')" for w in weekdays])
                blocks = response.xpath(f"//*[({weekday_expr})]")
                if blocks and len(blocks) > 0:
                    # take the nearest common ancestor of the first match
                    blk = blocks[0]
                    anc = blk.xpath("ancestor::div[(@class) and (string-length(normalize-space(.))>0)][1]")
                    if anc and len(anc) > 0:
                        inner = anc.get()
                        cleaned_html = (
                            '<!doctype html>'
                            '<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                            f'<title>Speiseplan - {source_url}</title>'
                            '</head><body>' + inner + '</body></html>'
                        )

            if cleaned_html:
                # Instead of producing cleaned HTML, extract all text nodes
                # and write each non-empty text fragment on its own line.
                try:
                    doc = lxml_html.fromstring(cleaned_html)
                    # remove script/style elements if present
                    for bad in doc.xpath('//script|//style'):
                        try:
                            bad.getparent().remove(bad)
                        except Exception:
                            pass
                    texts = [t.strip() for t in doc.itertext() if t and t.strip()]
                    cleaned_min = '\n'.join(texts)
                except Exception:
                    # fallback to raw HTML if parsing fails
                    cleaned_min = cleaned_html

                clean_name = f"cleaned_{filename}"
                clean_path = str(self.artifacts_dir / clean_name)
                try:
                    with open(clean_path, 'w', encoding='utf-8') as f:
                        f.write(cleaned_min)
                except Exception:
                    pass
            else:
                clean_path = None

        except Exception:
            clean_path = None

        yield {"pdf_page_path": full_path, "pdf_page_url": source_url, "clean_html_path": clean_path}
