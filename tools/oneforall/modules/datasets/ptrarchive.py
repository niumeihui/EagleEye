import random

from tools.oneforall.common import utils
from tools.oneforall.common.query import Query


class PTRArchive(Query):
    def __init__(self, domain):
        Query.__init__(self)
        self.domain = self.register(domain)
        self.module = 'Dataset'
        self.source = "PTRArchiveQuery"
        self.addr = 'http://ptrarchive.com/tools/search4.htm'

    def query(self):
        """
        向接口查询子域并做子域匹配
        """
        self.header = self.get_header()
        self.proxy = self.get_proxy(self.source)
        # 绕过主页前端JS验证
        self.cookie = {'pa_id': str(random.randint(0, 1000000000))}
        params = {'label': self.domain, 'date': 'ALL'}
        resp = self.get(self.addr, params)
        if not resp:
            return
        if resp.status_code == 200:
            subdomains = utils.match_subdomain(self.domain, resp.text)
            if subdomains:
                # 合并搜索子域名搜索结果
                self.subdomains = self.subdomains.union(subdomains)

    def run(self):
        """
        类执行入口
        """
        self.begin()
        self.query()
        self.finish()
        self.save_json()
        self.gen_result()
        self.save_db()


def do(domain):  # 统一入口名字 方便多线程调用
    """
    类统一调用入口

    :param str domain: 域名
    """
    query = PTRArchive(domain)
    query.run()


if __name__ == '__main__':
    do('example.com')
