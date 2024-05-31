# Standard Python libraries.
import asyncio
import logging
import random
import urllib

# Third party Python libraries.
import httpx
from bs4 import BeautifulSoup

# Custom Python libraries.

__version__ = "1.0"


def get_tbs(from_date, to_date):
    """Helper function to format the tbs parameter dates. Note that verbatim mode also uses the &tbs= parameter, but
    this function is just for customized search periods.

    :param datetime.date from_date: Python date object, e.g. datetime.date(2021, 1, 1)
    :param datetime.date to_date: Python date object, e.g. datetime.date 2021, 6, 1)

    :rtype: str
    :return: Dates encoded in tbs format.
    """

    from_date = from_date.strftime("%m/%d/%Y")
    to_date = to_date.strftime("%m/%d/%Y")

    formatted_tbs = f"cdr:1,cd_min:{from_date},cd_max:{to_date}"

    return formatted_tbs


class SearchClient:
    def __init__(
        self,
        query,
        tld="com",
        lang_html_ui="en",
        lang_result="lang_en",
        tbs="0",
        safe="off",
        start=0,
        num=100,
        country="",
        extra_params=None,
        max_search_result_urls_to_return=100,
        minimum_delay_between_paged_results_in_seconds=7,
        user_agent=None,
        manages_http_429s=True,
        http_429_cool_off_time_in_minutes=60,
        http_429_cool_off_factor=1.1,
        proxy="",
        verify_ssl=True,
        verbosity=5,
        verbose_output=False,
        google_exemption=None,
        logger=None,
    ) -> None:
        """
        SearchClient
        :param str query: Query string. Must NOT be url-encoded.
        :param str tld: Top level domain.
        :param str lang_html_ui: HTML User Interface language.
        :param str lang_result: Search result language. Exemplar languages: "lang_en" (English), "lang_de" (German). Info: https://www.google.com/advanced_search
        :param str tbs: Verbatim search or time limits (e.g., "qdr:h" => last hour, "qdr:d" => last 24 hours, "qdr:m"
            => last month).
        :param str safe: Safe search.
        :param int start: First page of results to retrieve.
        :param int num: Max number of results to pull back per page. Capped at 100 by Google.
        :param str country: Country or region to focus the search on. Similar to changing the TLD, but does not yield
            exactly the same results. Only Google knows why...
        :param dict extra_params: A dictionary of extra HTTP GET parameters, which must be URL encoded. For example if
            you don't want Google to filter similar results you can set the extra_params to {'filter': '0'} which will
            append '&filter=0' to every query.
        :param int max_search_result_urls_to_return: Max URLs to return for the entire Google search.
        :param int minimum_delay_between_paged_results_in_seconds: Minimum time to wait between HTTP requests for
            consecutive pages for the same search query. The actual time will be a random value between this minimum
            value and value + 11 to make it look more human.
        :param str user_agent: Hard-coded user agent for the HTTP requests.
        :param bool manages_http_429s: Determines if googleserp will handle HTTP 429 cool off and
           retries. Disable if you want to manage HTTP 429 responses.
        :param int http_429_cool_off_time_in_minutes: Minutes to sleep if an HTTP 429 is detected.
        :param float http_429_cool_off_factor: Factor to multiply by http_429_cool_off_time_in_minutes for each HTTP 429
            detected.
        :param str proxy: HTTP(S) or SOCKS5 proxy to use.
        :param bool verify_ssl: Verify the SSL certificate to prevent traffic interception attacks. Defaults to True.
            This may need to be disabled in some HTTPS proxy instances.
        :param int verbosity: Logging and console output verbosity.
        :param bool verbose_output: False (only URLs) or True (rank, title, description, and URL). Defaults to False.
        :param str google_exemption: Google cookie exemption string. This is a string that Google uses to allow certain
            google searches. Defaults to None.
        :param logging.Logger logger: Logger object to use. Defaults to None.

        :rtype: List of str
        :return: List of URLs found or list of {"rank", "title", "description", "url"}
        """

        self.query = urllib.parse.quote_plus(query)
        self.tld = tld
        self.lang_html_ui = lang_html_ui
        self.lang_result = lang_result.lower()
        self.tbs = tbs
        self.safe = safe
        self.start = start
        self.num = num
        self.country = country
        self.extra_params = extra_params
        self.max_search_result_urls_to_return = max_search_result_urls_to_return
        self.minimum_delay_between_paged_results_in_seconds = minimum_delay_between_paged_results_in_seconds
        self.user_agent = user_agent
        self.manages_http_429s = manages_http_429s
        self.http_429_cool_off_time_in_minutes = http_429_cool_off_time_in_minutes
        self.http_429_cool_off_factor = http_429_cool_off_factor
        self.proxy = proxy
        self.verify_ssl = verify_ssl
        self.verbosity = verbosity
        self.verbose_output = verbose_output
        self.google_exemption = google_exemption

        self.logger = logger

        if not self.logger:
            self.logger = logging.getLogger("googleserp")
            log_formatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)s] %(message)s")
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(log_formatter)
            self.logger.addHandler(console_handler)

        # Assign log level.
        self.logger.setLevel((6 - self.verbosity) * 10)

        if self.num > 100:
            self.logger.warning("The largest value allowed by Google for num is 100. Setting num to 100.")
            self.num = 100

        if 400 < self.max_search_result_urls_to_return:
            self.logger.warning(
                "googleserp is usually only able to retrieve a maximum of ~400 results. See README for more details."
            )

        # Populate cookies with GOOGLE_ABUSE_EXEMPTION if it is provided. Otherwise, initialize cookies to None.
        # It will be updated with each request in get_page().
        if self.google_exemption:
            self.cookies = {
                "GOOGLE_ABUSE_EXEMPTION": self.google_exemption,
            }
        else:
            self.cookies = None

        # Used later to ensure there are not any URL parameter collisions.
        self.url_parameters = (
            "btnG",
            "cr",
            "hl",
            "num",
            "q",
            "safe",
            "start",
            "tbs",
            "lr",
        )

        # Default user agent, unless instructed by the user to change it.
        if not user_agent:
            self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36"

        # Update the URLs with the initial SearchClient attributes.
        self.update_urls()

        # Initialize proxy_dict.
        self.proxy_dict = {}

        # Update proxy_dict if a proxy is provided.
        if proxy:
            self.proxy_dict = {
                "http": self.proxy,
                "https": self.proxy,
            }

    def update_urls(self) -> None:
        """Update search URLs being used."""

        # URL templates to make Google searches.
        self.url_home = f"https://www.google.{self.tld}/"

        # First search requesting the default 10 search results.
        self.url_search = (
            f"https://www.google.{self.tld}/search?hl={self.lang_html_ui}&lr={self.lang_result}&"
            f"q={self.query}&btnG=Google+Search&tbs={self.tbs}&safe={self.safe}&"
            f"cr={self.country}&filter=0"
        )

        # Subsequent searches starting at &start= and retrieving 10 search results at a time.
        self.url_next_page = (
            f"https://www.google.{self.tld}/search?hl={self.lang_html_ui}&lr={self.lang_result}&"
            f"q={self.query}&start={self.start}&tbs={self.tbs}&safe={self.safe}&"
            f"cr={self.country}&filter=0"
        )

        # First search requesting more than the default 10 search results.
        self.url_search_num = (
            f"https://www.google.{self.tld}/search?hl={self.lang_html_ui}&lr={self.lang_result}&"
            f"q={self.query}&num={self.num}&btnG=Google+Search&tbs={self.tbs}&"
            f"safe={self.safe}&cr={self.country}&filter=0"
        )

        # Subsequent searches starting at &start= and retrieving &num= search results at a time.
        self.url_next_page_num = (
            f"https://www.google.{self.tld}/search?hl={self.lang_html_ui}&lr={self.lang_result}&"
            f"q={self.query}&start={self.start}&num={self.num}&tbs={self.tbs}&"
            f"safe={self.safe}&cr={self.country}&filter=0"
        )

    def filter_search_result_urls(self, link):
        """Filter links found in the Google result pages HTML code. Valid results are absolute URLs not pointing to a
        Google domain, like images.google.com or googleusercontent.com. Returns None if the link doesn't yield a valid
        result.

        :rtype: str
        :return: URL string
        """

        self.logger.debug(f"pre filter_search_result_urls() link: {link}")

        try:
            # Extract URL from parameter. Once in a while the full "http://www.google.com/url?" exists instead of just
            # "/url?". After a re-run, it disappears and "/url?" is present...might be a caching thing?
            if link.startswith("/url?") or link.startswith("http://www.google.com/url?"):
                urlparse_object = urllib.parse.urlparse(link, scheme="http")

                # The "q" key exists most of the time.
                try:
                    link = urllib.parse.parse_qs(urlparse_object.query)["q"][0]
                # Sometimes, only the "url" key does though.
                except KeyError:
                    link = urllib.parse.parse_qs(urlparse_object.query)["url"][0]

            # Create a urlparse object.
            urlparse_object = urllib.parse.urlparse(link, scheme="http")

            # Exclude urlparse objects without a netloc value.
            if not urlparse_object.netloc:
                self.logger.debug(
                    f"Excluding URL because it does not contain a urllib.parse.urlparse netloc value: {link}"
                )
                link = None

            # TODO: Generates false positives if specifying an actual Google site, e.g. "site:google.com fiber".
            if urlparse_object.netloc and ("google" in urlparse_object.netloc.lower()):
                self.logger.debug(f'Excluding URL because it contains "google": {link}')
                link = None

        except Exception:
            link = None

        self.logger.debug(f"post filter_search_result_urls() link: {link}")

        return link

    def http_429_detected(self) -> None:
        """Increase the HTTP 429 cool off period."""

        new_http_429_cool_off_time_in_minutes = round(
            self.http_429_cool_off_time_in_minutes * self.http_429_cool_off_factor,
            2,
        )
        self.logger.info(
            f"Increasing HTTP 429 cool off time by a factor of {self.http_429_cool_off_factor}, "
            f"from {self.http_429_cool_off_time_in_minutes} minutes to {new_http_429_cool_off_time_in_minutes} minutes"
        )
        self.http_429_cool_off_time_in_minutes = new_http_429_cool_off_time_in_minutes

    async def get_page(self, url):
        """Request the given URL and return the response page.

        :param str url: URL to retrieve.

        :rtype: str
        :return: Web page HTML retrieved for the given URL
        """

        headers = {
            "User-Agent": self.user_agent,
        }

        self.logger.info(f"Requesting URL: {url}")

        async with httpx.AsyncClient(proxies=self.proxy_dict, cookies=self.cookies, verify=self.verify_ssl) as client:
            response = await client.get(url, headers=headers, timeout=15)

            # Update the cookies.
            self.cookies = response.cookies

            # Extract the HTTP response code.
            http_response_code = response.status_code

            # debug_requests_response(response)
            self.logger.debug(f"    status_code: {http_response_code}")
            self.logger.debug(f"    headers: {headers}")
            self.logger.debug(f"    cookies: {self.cookies}")
            self.logger.debug(f"    proxy: {self.proxy}")
            self.logger.debug(f"    verify_ssl: {self.verify_ssl}")

            # Google throws up a consent page for searches sourcing from a European Union country IP location.
            # See https://github.com/benbusby/whoogle-search/issues/311
            try:
                if response.cookies["CONSENT"].startswith("PENDING+"):
                    self.logger.warning(
                        "Looks like your IP address is sourcing from a European Union location...your search results may "
                        "vary, but I'll try and work around this by updating the cookie."
                    )

                    # Convert the cookiejar data structure to a Python dict.
                    cookie_dict = httpx.cookies.jar.CookiesJar(response.cookies)

                    # Pull out the random number assigned to the response cookie.
                    number = cookie_dict["CONSENT"].split("+")[1]

                    # See https://github.com/benbusby/whoogle-search/pull/320/files
                    """
                    Attempting to dissect/breakdown the new cookie response values.

                    YES - Accept consent
                    shp - ?
                    gws - "server:" header value returned from original request. Maybe Google Workspace plus a build?
                    fr - Original tests sourced from France. Assuming this is the country code. Country code was changed
                        to .de and it still worked.
                    F - FX agrees to tracking. Modifying it to just F seems to consent with "no" to personalized stuff.
                        Not tested, solely based off of
                        https://github.com/benbusby/whoogle-search/issues/311#issuecomment-841065630
                    XYZ - Random 3-digit number assigned to the first response cookie.
                    """
                    self.cookies = {"CONSENT": f"YES+shp.gws-20211108-0-RC1.fr+F+{number}"}

                    self.logger.info(f"Updating cookie to: {self.cookies}")

            # "CONSENT" cookie does not exist.
            except KeyError:
                pass

            html = ""

            if http_response_code == 200:
                html = response.text

            elif http_response_code == 429:
                self.logger.warning(
                    "Google is blocking your IP for making too many requests in a specific time period."
                )

                # Calling script does not want googleserp to handle HTTP 429 cool off and retry. Just return a
                # notification string.
                if not self.manages_http_429s:
                    self.logger.info("Since manages_http_429s=False, googleserp is done.")
                    return "HTTP_429_DETECTED"

                self.logger.info(f"Sleeping for {self.http_429_cool_off_time_in_minutes} minutes...")
                await asyncio.sleep(self.http_429_cool_off_time_in_minutes * 60)
                self.http_429_detected()

                # Try making the request again.
                html = await self.get_page(url)

            else:
                self.logger.warning(f"HTML response code: {http_response_code}")

        return html

    async def search(self):
        """Start the Google search.

        :rtype: List of str
        :return: List of URLs found or list of {"rank", "title", "description", "url"}
        """

        # Consolidate search results.
        self.search_result_list = []

        # Count the number of valid, non-duplicate links found.
        total_valid_links_found = 0

        # If no extra_params is given, create an empty dictionary. We should avoid using an empty dictionary as a
        # default value in a function parameter in Python.
        if not self.extra_params:
            self.extra_params = {}

        # Check extra_params for overlapping parameters.
        for builtin_param in self.url_parameters:
            if builtin_param in self.extra_params.keys():
                raise ValueError(f'GET parameter "{builtin_param}" is overlapping with the built-in GET parameter')

        # Simulates browsing to the https://www.google.com home page and retrieving the initial cookie.
        html = await self.get_page(self.url_home)

        # Loop until we reach the maximum result results found or there are no more search results found to reach
        # max_search_result_urls_to_return.
        while total_valid_links_found <= self.max_search_result_urls_to_return:
            self.logger.info(
                f"Stats: start={self.start}, num={self.num}, total_valid_links_found={total_valid_links_found} / "
                f"max_search_result_urls_to_return={self.max_search_result_urls_to_return}"
            )

            # Prepare the URL for the search request.
            if self.start:
                if self.num == 10:
                    url = self.url_next_page
                else:
                    url = self.url_next_page_num
            else:
                if self.num == 10:
                    url = self.url_search
                else:
                    url = self.url_search_num

            # Append extra GET parameters to the URL. This is done on every iteration because we're rebuilding the
            # entire URL at the end of this loop. The keys and values are not URL encoded.
            for key, value in self.extra_params.items():
                url += f"&{key}={value}"

            # Request Google search results.
            html = await self.get_page(url)

            # HTTP 429 message returned from get_page() function, add "HTTP_429_DETECTED" to the set and return to the
            # calling script.
            if html == "HTTP_429_DETECTED":
                self.search_result_list.append("HTTP_429_DETECTED")
                return self.search_result_list

            # Create the BeautifulSoup object.
            soup = BeautifulSoup(html, "html.parser")

            # Find all HTML <a> elements.
            try:
                anchors = soup.find(id="search").find_all("a")
            # Sometimes (depending on the User-Agent) there is no id "search" in html response.
            except AttributeError:
                # Remove links from the top bar.
                gbar = soup.find(id="gbar")
                if gbar:
                    gbar.clear()
                anchors = soup.find_all("a")

            # Tracks number of valid URLs found on a search page.
            valid_links_found_in_this_search = 0

            # Process every anchored URL.
            for a in anchors:
                # Get the URL from the anchor tag.
                try:
                    link = a["href"]
                except KeyError:
                    self.logger.warning(f"No href for link: {link}")
                    continue

                # Filter invalid links and links pointing to Google itself.
                link = self.filter_search_result_urls(link)
                if not link:
                    continue

                if self.verbose_output:
                    # Extract the URL title.
                    try:
                        title = a.get_text()
                    except Exception:
                        self.logger.warning(f"No title for link: {link}")
                        title = ""

                    # Extract the URL description.
                    try:
                        description = a.parent.parent.contents[1].get_text()

                        # Sometimes Google returns different structures.
                        if description == "":
                            description = a.parent.parent.contents[2].get_text()

                    except Exception:
                        self.logger.warning(f"No description for link: {link}")
                        description = ""

                # Check if URL has already been found.
                if link not in self.search_result_list:
                    # Increase the counters.
                    valid_links_found_in_this_search += 1
                    total_valid_links_found += 1

                    self.logger.info(f"Found unique URL #{total_valid_links_found}: {link}")

                    if self.verbose_output:
                        self.search_result_list.append(
                            {
                                "rank": total_valid_links_found,  # Approximate rank according to googleserp.
                                "title": title.strip(),  # Remove leading and trailing spaces.
                                "description": description.strip(),  # Remove leading and trailing spaces.
                                "url": link,
                            }
                        )
                    else:
                        self.search_result_list.append(link)

                else:
                    self.logger.info(f"Duplicate URL found: {link}")

                # If we reached the limit of requested URLs, return with the results.
                if self.max_search_result_urls_to_return <= len(self.search_result_list):
                    return self.search_result_list

            # Determining if a "Next" URL page of results is not straightforward. If no valid links are found, the
            # search results have been exhausted.
            if valid_links_found_in_this_search == 0:
                self.logger.info("No valid search results found on this page. Moving on...")
                return self.search_result_list

            # Bump the starting page URL parameter for the next request.
            self.start += self.num

            # Refresh the URLs.
            self.update_urls()

            # If self.num == 10, this is the default search criteria.
            if self.num == 10:
                url = self.url_next_page
            # User has specified search criteria requesting more than 10 results at a time.
            else:
                url = self.url_next_page_num

            # Randomize sleep time between paged requests to make it look more human.
            random_sleep_time = random.choice(
                range(
                    self.minimum_delay_between_paged_results_in_seconds,
                    self.minimum_delay_between_paged_results_in_seconds + 11,
                )
            )
            self.logger.info(f"Sleeping {random_sleep_time} seconds until retrieving the next page of results...")
            await asyncio.sleep(random_sleep_time)
