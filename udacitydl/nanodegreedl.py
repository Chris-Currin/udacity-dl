import os
from collections import OrderedDict

from courses import COURSES_DICT
from multiprocessing import Process, Manager

from utils import read_json, dump_json, clean_filename, download_file


def multi_conditions(*conditions):
    def iter_conditions(driver):
        for condition in conditions:
            try:
                res = condition(driver)
                if res: return res
            except:
                pass

    return iter_conditions


def page_has_loaded(driver):
    page_state = driver.execute_script('return document.readyState;')
    return page_state == 'complete'


def wait_for_not_loading(driver):
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import StaleElementReferenceException
    try:
        element_text = EC.title_contains('Loading')(driver) or EC.title_is('Udacity')(driver)
        return not element_text
    except StaleElementReferenceException:
        return False


class UdacityNanodegreeDownloader(object):
    """
    Class to download content (videos, lecture notes, ...) from udacity.com for
    use offline.
    """

    CLASSROOM_URL = 'https://classroom.udacity.com/me'
    BASE_URL = 'https://classroom.udacity.com/nanodegrees/%s'
    EXTRACURRICULAR_URL = 'https://classroom.udacity.com/nanodegrees/%s/syllabus/extracurricular'
    DOWNLOAD_URL = BASE_URL + '/downloads'

    def __init__(self, headless=True, email=None, password=None, implicit_wait=5):
        from selenium import webdriver
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('headless')
        options.add_argument('--log-level=3')
        self.browser = webdriver.Chrome(options=options)
        self.browser.implicitly_wait(implicit_wait)  # seconds
        self.email = email
        self.password = password
        self._load_home()

    def __del__(self):
        self.browser.close()

    def _load_home(self):
        """Load the user's classroom (will likely need to sign in too)"""
        from selenium.webdriver.support import expected_conditions
        home_title_present = expected_conditions.title_contains('Home')
        self._load_page(self.CLASSROOM_URL, home_title_present)
        assert "Home" in self.browser.title

    def _load_page(self, url, *conditions, timeout=100):
        from selenium.webdriver.support.wait import WebDriverWait
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.support import expected_conditions
        login_title_present = expected_conditions.title_contains('Sign In')
        if url is not None and url != '':
            self.browser.get(url)
            all_conditions = list(conditions) + [login_title_present]
        else:
            all_conditions = conditions
        try:
            WebDriverWait(self.browser, timeout).until(multi_conditions(*all_conditions))
        except TimeoutException:
            print("%s not loaded" % self.browser.current_url)
            print(all_conditions)
            print(self.browser.title)
            raise
        print("%s loaded" % self.browser.current_url)
        if "Sign In" in self.browser.title:
            from getpass import getpass
            # The email or password you entered is invalid
            print("you need to sign in first, please enter your details as prompted")
            email_form = self.browser.find_element_by_xpath("//input[contains(@type,'email')]")
            pw_form = self.browser.find_element_by_xpath("//input[contains(@type,'password')]")
            submit_button = self.browser.find_elements_by_xpath("//button[contains(text(), 'Sign In')]")[1]
            print()
            email = self.email or input("email address:")
            pw = self.password or getpass("password:")
            email_form.send_keys(email)
            pw_form.send_keys(pw)
            submit_button.click()
            self._load_page(None, *conditions, timeout=timeout)
        assert "Loading" not in self.browser.title

    def get_nanodegree_url_from_name(self, nanodegree_symbol):
        """Given the short code of a nanodegree, return the syllabus url"""
        return self.BASE_URL % nanodegree_symbol

    def get_download_url_from_name(self, course_name):
        """Given the name of a course, return the video lecture url"""
        return self.DOWNLOAD_URL % course_name

    def find_element_by_id_not_stale(self, id_str, iter=0, max_iter=10):
        from selenium.common.exceptions import StaleElementReferenceException
        main_content = self.browser.find_element_by_id(id_str)
        try:
            if main_content.is_enabled():
                return main_content
            else:
                raise Exception("not enabled")
        except StaleElementReferenceException:
            if iter < max_iter:
                return self.find_element_by_id_not_stale(id_str, iter + 1, max_iter=max_iter)
            else:
                raise Exception("still stale after %d iterations" % max_iter)

    def get_downloadable_content(self, nd_code, nd_url, dl_only=None):
        """Iterate through the course for links to download"""
        from selenium.common.exceptions import WebDriverException, NoSuchElementException, StaleElementReferenceException

        # load the main course page
        self._load_page(nd_url, wait_for_not_loading)
        long_course_name = COURSES_DICT.get(nd_code, nd_code)
        try:
            if long_course_name == nd_code:
                show_nav = self.browser.find_elements_by_xpath('//a[contains(@title,"Show Navigations")]')
                if len(show_nav) > 0:
                    self.browser.execute_script("arguments[0].click();", show_nav[0])
                long_course_name = self.browser.find_element_by_id('main-layout-sidebar') \
                    .find_element_by_tag_name('h4').text
        except ValueError:
            print('Course code not valid')
        print('* Collecting downloadable content for %s from %s' % (long_course_name, nd_code))

        # get all the Term sections
        main_content = self.browser.find_element_by_id('main-layout-content')
        term_headings = main_content.find_elements_by_tag_name('h2')
        term_links = OrderedDict()
        for heading in term_headings:
            try:
                heading_link = heading.find_element_by_tag_name('a')
                term_links[heading_link.text] = heading_link.get_attribute('href')
            except NoSuchElementException:
                pass

        # get all the extracurricular sections
        try:
            self._load_page(self.EXTRACURRICULAR_URL % nd_code, wait_for_not_loading)
            main_content = self.browser.find_element_by_id('main-layout-content')
            extra_headings = main_content.find_elements_by_tag_name('h2')
            for heading in extra_headings:
                try:
                    heading_link = heading.find_element_by_tag_name('a')
                    term_links[heading_link.text] = heading_link.get_attribute('href')
                except NoSuchElementException:
                    pass
        except StaleElementReferenceException:
            pass

        # only download certain sections
        if dl_only is not None:
            if type(dl_only) is not list:
                dl_only = [dl_only]
            # restrict to download only passed terms ("01","2","3",etc.)
            dl_only_terms = set()
            for dl in dl_only:
                if "." not in dl:
                    dl_only_terms.add(int(dl))
                else:
                    dl_only_terms.add(int(dl[:dl.find(".")]))
                assert float(dl), "index (%s) not valid" % dl

            for i, term_key in enumerate(term_links):
                if i+1 not in dl_only_terms:
                    term_links[term_key] = None

        # load lesson links if run previously
        nd_links = read_json(nd_code) if os.path.exists(nd_code + '.json') else {}
        # get links to lessons for the term
        for core_i, (core_name, core_href) in enumerate(term_links.items()):
            if core_href is None:
                continue
            print("gathering lesson links from... %02d %s" % (core_i + 1, core_name))
            core_index = '%02d %s' % (core_i + 1, core_name)
            if core_index in nd_links and nd_links[core_index]['link'] == core_href and len(nd_links[core_index]) > 1:
                continue
            nd_links[core_index] = {'link': core_href}
            try:
                self._load_page(core_href, wait_for_not_loading)
            except AssertionError:
                print("skipped due to loading error")
                continue

            lessons = None
            iter_i = 0
            max_iter = 10
            while lessons is None and iter_i < max_iter:
                try:
                    main_content = self.browser.find_element_by_id('main-layout-content')
                    lessons = main_content.find_elements_by_tag_name('li')
                except StaleElementReferenceException:
                    iter_i += 1

            assert type(lessons) is list, "lessons not loaded from main-layout-content"
            for li, lesson in enumerate(lessons):
                link = lesson.find_element_by_tag_name("a")
                link_href = link.get_attribute('href')
                # lesson_type = lesson.find_element_by_tag_name('h5').text
                lesson_name = '%02d.%02d - %s' % (core_i + 1, li + 1, lesson.find_element_by_tag_name('h4').text)
                if link_href.endswith('#'):
                    # open closed card (doesn't always work)
                    try:
                        link.click()
                    except WebDriverException:
                        try:
                            lesson.click()
                        except WebDriverException:
                            self.browser.execute_script("arguments[0].click();", link)
                    link = lesson.find_element_by_tag_name("a")
                    link_href = link.get_attribute('href')
                if lesson_name not in nd_links[core_index] or nd_links[core_index][lesson_name]['link'] != link_href:
                    nd_links[core_index][lesson_name] = {'link': link_href}

            print("collected")

        # save lesson links
        dump_json(nd_code, nd_links)
        # get links for downloadable content (e.g. .zip files)
        for core_name, core_dict in nd_links.items():
            for lesson_name, lesson_dict in core_dict.items():
                if lesson_name.endswith('link'):
                    continue
                if dl_only is not None:
                    lesson_idx = float(lesson_name[:lesson_name.find(" - ")])
                    found = False
                    for dl in dl_only:
                        if float(dl) == lesson_idx:
                            found = True
                            break
                    if not found:
                        continue

                print("gathering download links from lesson... %s" % lesson_name)
                if len(nd_links[core_name][lesson_name]) == 1:
                    try:
                        self._load_page(lesson_dict['link'], wait_for_not_loading)
                    except AssertionError:
                        print("skipped due to loading error")
                        continue
                    show_nav = self.browser.find_elements_by_xpath('//a[contains(@title,"Show Navigations")]')
                    if len(show_nav) > 0:
                        self.browser.execute_script("arguments[0].click();", show_nav[0])
                    try:
                        notebook_iframe = self.browser.find_element_by_xpath('//iframe[contains(@src,".ipynb")]')
                        nd_links[core_name][lesson_name][notebook_iframe.get_attribute('src')] = False
                    except:
                        pass

                    sidebar = self.browser.find_element_by_id('main-layout-sidebar')
                    resources = sidebar.find_elements_by_tag_name('h2')[1]
                    self.browser.execute_script("arguments[0].click();", resources)
                    tree_resources = self.browser.find_element_by_id('tree-resources')
                    links = tree_resources.find_elements_by_xpath("//a[contains(@href,'.zip')]")
                    for link in links:
                        nd_links[core_name][lesson_name][link.get_attribute('href')] = False
        dump_json(nd_code, nd_links)
        return nd_links, long_course_name

    def download_nanodegree(self, nd_code, dest_dir='.', dl_only=None, force=False, **kwargs):
        """Download all the contents (quizzes, videos, lecture notes, ...) of the course to the given destination
        directory (defaults to .)
        Lesson values in dl_only need to include a leading 0 if <10.
        """

        course_home_url = self.get_nanodegree_url_from_name(nd_code)
        print('* Need to download from ', course_home_url)

        download_dict, long_cname = self.get_downloadable_content(nd_code, course_home_url, dl_only=dl_only, **kwargs)

        print('* Got all downloadable content for ' + long_cname)

        course_dir = os.path.abspath(os.path.join(dest_dir, long_cname))

        print('* ' + nd_code + ' will be downloaded to ' + course_dir)

        # download the standard pages
        print(' - Downloading zipped/videos pages')

        if dl_only is not None and type(dl_only) is not list:
            dl_only = [dl_only]

        for core_name, lesson_links in download_dict.items():
            core_name = clean_filename(core_name)
            core_dir = os.path.join(course_dir, core_name)
            # keep only valid ascii chars
            if not os.path.exists(core_dir):
                os.makedirs(core_dir)
            print(' -- Downloading %s' % core_name)
            for lesson_name, lesson_dict in lesson_links.items():
                if lesson_name == 'link':
                    continue
                if dl_only is not None:
                    lesson_idx = float(lesson_name[:lesson_name.find(" - ")])
                    found = False
                    for dl in dl_only:
                        if float(dl) == lesson_idx:
                            found = True
                            break
                    if not found:
                        continue

                print(' --- Downloading %s' % lesson_name)
                for link, downloaded in lesson_dict.items():
                    if downloaded:
                        continue
                    try:
                        fname = lesson_name[:lesson_name.find(" ")] + "-" + link.split('/')[-1]
                        print('     * Downloading ', fname, '...')
                        download_file(link, core_dir, fname, force=force)
                        download_dict[core_name][lesson_name][link] = True
                    except Exception as e:
                        print('     ! failed with error:')
                        print(e)
        dump_json(nd_code, download_dict)
