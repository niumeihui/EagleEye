#!/usr/bin/python3
# coding=utf-8

"""
OneForAll是一款功能强大的子域收集工具

:copyright: Copyright (c) 2019, Jing Ling. All rights reserved.
:license: GNU General Public License v3.0, see LICENSE for more details.
"""

import asyncio

import fire
from config import Oneforall
from tools.oneforall import dbexport
from datetime import datetime
from web.utils.logs import logger
from tools.oneforall.collect import Collect
from tools.oneforall.aiobrute import AIOBrute
from tools.oneforall.common import utils, resolve, request
from tools.oneforall.common.database import Database
from tools.oneforall.takeover import Takeover

yellow = '\033[01;33m'
white = '\033[01;37m'
green = '\033[01;32m'
blue = '\033[01;34m'
red = '\033[1;31m'
end = '\033[0m'

version = 'v0.0.9#dev'
message = white + '{' + red + version + white + '}'

banner = f"""
OneForAll是一款功能强大的子域收集工具{yellow}
             ___             _ _ 
 ___ ___ ___|  _|___ ___ ___| | | {message}{green}
| . |   | -_|  _| . |  _| .'| | | {blue}
|___|_|_|___|_| |___|_| |__,|_|_| {white}git.io/fjHT1

{red}OneForAll处于开发中，会进行版本快速迭代，请每次在使用前进行更新！{end}
"""


class OneForAll(object):
    """
    OneForAll帮助信息

    OneForAll是一款功能强大的子域收集工具

    Example:
        python3 oneforall.py version
        python3 oneforall.py --target example.com run
        python3 oneforall.py --target ./domains.txt run
        python3 oneforall.py --target example.com --valid None run
        python3 oneforall.py --target example.com --brute True run
        python3 oneforall.py --target example.com --port medium run
        python3 oneforall.py --target example.com --format csv run
        python3 oneforall.py --target example.com --dns False run
        python3 oneforall.py --target example.com --req False run
        python3 oneforall.py --target example.com --takeover False run
        python3 oneforall.py --target example.com --show True run

    Note:
        参数valid可选值1，0，None分别表示导出有效，无效，全部子域
        参数port可选值有'default', 'small', 'large', 详见config.py配置
        参数format可选格式有'txt', 'rst', 'csv', 'tsv', 'json', 'yaml', 'html',
                          'jira', 'xls', 'xlsx', 'dbf', 'latex', 'ods'
        参数path默认None使用OneForAll结果目录生成路径

    :param str target:     单个域名或者每行一个域名的文件路径(必需参数)
    :param bool brute:     使用爆破模块(默认False)
    :param bool dns:       DNS解析子域(默认True)
    :param bool req:       HTTP请求子域(默认True)
    :param str port:       请求验证子域的端口范围(默认只探测80端口)
    :param int valid:      导出子域的有效性(默认None)
    :param str format:     导出文件格式(默认csv)
    :param str path:       导出文件路径(默认None)
    :param bool takeover:  检查子域接管(默认False)
    :param bool show:      终端显示导出数据(默认False)
    """
    def __init__(self, target, brute=None, dns=None, req=None,
                 port='default', valid=None, format='csv', path=None,
                 takeover=False, show=False):
        self.target = target
        self.port = port
        self.domains = set()
        self.domain = str()
        self.data = list()
        self.datas = list()
        self.brute = brute
        self.dns = dns
        self.req = req
        self.takeover = takeover
        self.valid = valid
        self.format = format
        self.path = path
        self.show = show

    def main(self):
        if self.brute is None:
            self.brute = Oneforall.enable_brute_module
        if self.dns is None:
            self.dns = Oneforall.enable_dns_resolve
        if self.req is None:
            self.req = Oneforall.enable_http_request
        old_table = self.domain + '_last_result'
        new_table = self.domain + '_now_result'
        collect = Collect(self.domain, export=False)
        collect.run()
        if self.brute:
            # 由于爆破会有大量dns解析请求 并发爆破可能会导致其他任务中的网络请求异常
            brute = AIOBrute(self.domain, export=False)
            brute.run()

        db = Database()
        original_table = self.domain + '_original_result'
        db.copy_table(self.domain, original_table)
        db.remove_invalid(self.domain)
        db.deduplicate_subdomain(self.domain)

        old_data = []
        # 非第一次收集子域的情况时数据库预处理
        if db.exist_table(new_table):
            db.drop_table(old_table)  # 如果存在上次收集结果表就先删除
            db.rename_table(new_table, old_table)  # 新表重命名为旧表
            old_data = db.get_data(old_table).as_dict()

        # 不解析子域直接导出结果
        if not self.dns:
            # 数据库导出
            dbexport.export(self.domain, valid=self.valid,
                            format=self.format, show=self.show)
            db.drop_table(new_table)
            db.rename_table(self.domain, new_table)
            db.close()
            return
        self.data = db.get_data(self.domain).as_dict()

        # 标记新发现子域
        self.data = utils.mark_subdomain(old_data, self.data)

        # 获取事件循环
        loop = asyncio.get_event_loop()
        asyncio.set_event_loop(loop)

        # 解析子域
        task = resolve.bulk_resolve(self.data)
        self.data = loop.run_until_complete(task)

        # 保存解析结果
        resolve_table = self.domain + '_resolve_result'
        db.drop_table(resolve_table)
        db.create_table(resolve_table)
        db.save_db(resolve_table, self.data, 'resolve')

        # 不请求子域直接导出结果
        if not self.req:
            # 数据库导出
            dbexport.Warehouse(resolve_table, self.domain)
            db.drop_table(new_table)
            db.rename_table(self.domain, new_table)
            db.close()
            return True

        # 请求子域
        task = request.bulk_request(self.data, self.port)
        self.data = loop.run_until_complete(task)
        self.datas.extend(self.data)
        # 在关闭事件循环前加入一小段延迟让底层连接得到关闭的缓冲时间
        loop.run_until_complete(asyncio.sleep(0.25))
        count = utils.count_valid(self.data)
        logger.log('INFOR', f'经验证{self.domain}有效子域{count}个')

        # 保存请求结果
        db.clear_table(self.domain)
        db.save_db(self.domain, self.data, 'request')

        # 数据库导出
        dbexport.export(self.domain, valid=self.valid,
                        format=self.format, show=self.show)
        db.drop_table(new_table)
        db.rename_table(self.domain, new_table)
        db.close()

        # 子域接管检查
        if self.takeover:
            subdomains = set(map(lambda x: x.get('subdomain'), self.data))
            takeover = Takeover(subdomains)
            takeover.run()

    def run(self):
        # print(banner)
        # dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # print(f'[*] Starting OneForAll @ {dt}\n')
        # logger.log('DEBUG', 'Python ' + utils.python_version())
        # logger.log('DEBUG', 'OneForAll ' + version)
        logger.log('INFOR', f'开始运行OneForAll')
        self.domains = utils.get_domains(self.target)
        if self.domains:
            for self.domain in self.domains:
                self.main()
            utils.export_all(self.format, self.path, self.datas)
        else:
            logger.log('FATAL', f'获取域名失败')
        logger.log('INFOR', f'结束运行OneForAll')

    @staticmethod
    def version():
        print(banner)
        exit(0)


if __name__ == '__main__':
    fire.Fire(OneForAll)
    #OneForAll('xxxx.cn').run()
    # OneForAll('./domains.txt').run()
