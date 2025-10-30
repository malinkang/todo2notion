import logging
import os
import re
import time

from notion_client import Client
from retrying import retry
from datetime import datetime, timedelta

from todo2notion.utils import (
    format_date,
    get_date,
    get_first_and_last_day_of_month,
    get_first_and_last_day_of_week,
    get_first_and_last_day_of_year,
    get_icon,
    get_relation,
    get_title,
    get_property_value
)
from dotenv import load_dotenv

load_dotenv()
TAG_ICON_URL = "https://www.notion.so/icons/tag_gray.svg"
USER_ICON_URL = "https://www.notion.so/icons/user-circle-filled_gray.svg"
TARGET_ICON_URL = "https://www.notion.so/icons/target_red.svg"
BOOKMARK_ICON_URL = "https://www.notion.so/icons/bookmark_gray.svg"


class NotionHelper:
    database_name_dict = {
        "TODO_DATABASE_NAME": "任务",
        "SETTING_DATABASE_NAME": "设置",
    }
    database_id_dict = {}
    todo_heatmap_block_id = None
    tomato_heatmap_block_id = None
    property_dict = {}
    def __init__(self):
        self.client = Client(auth=os.getenv("NOTION_TOKEN"), log_level=logging.ERROR)
        self.__cache = {}
        self.page_id = self.extract_page_id(os.getenv("NOTION_PAGE"))
        self.search_database(self.page_id)
        for key in self.database_name_dict.keys():
            if os.getenv(key) != None and os.getenv(key) != "":
                self.database_name_dict[key] = os.getenv(key)
        self.todo_database_id = self.database_id_dict.get(
            self.database_name_dict.get("TODO_DATABASE_NAME")
        )     
        self.setting_database_id = self.database_id_dict.get(
            self.database_name_dict.get("SETTING_DATABASE_NAME")
        )   
        r = self.client.databases.retrieve(database_id=self.todo_database_id)
        for key,value in r.get("properties").items():
            self.property_dict[key] = value
        self.project_database_id = self.get_relation_database_id(self.property_dict.get("清单"))
        self.tag_database_id = self.get_relation_database_id(self.property_dict.get("标签"))
        self.day_database_id = self.get_relation_database_id(self.property_dict.get("日"))
        self.week_database_id = self.get_relation_database_id(self.property_dict.get("周"))
        self.month_database_id = self.get_relation_database_id(self.property_dict.get("月"))
        self.year_database_id = self.get_relation_database_id(self.property_dict.get("年"))
        self.all_database_id = self.get_relation_database_id(self.property_dict.get("全部"))
        if self.day_database_id:
            self.write_database_id(self.day_database_id)
        self.config = self.query_setting_data()
   
            
    
    def query_setting_data(self):
        """从设置数据库中查询标题为设置的数据"""
        result = {}
        query_filter = {
            "property": "标题",
            "title": {
                "equals": "设置"
            }
        }
        response = self.client.databases.query(
            database_id=self.setting_database_id,
            filter=query_filter
        )
        results = response.get("results")
        if results:
            for key,value in results[0].get("properties").items():
               result[key] = get_property_value(value)
        return result
    
    def get_property_type(self,database_id):
        """获取一个database的property和类型的映射关系"""
        result = {}
        r = self.client.databases.retrieve(database_id=database_id)
        for key,value in r.get("properties").items():
            result[key] = value.get("type")
        return result
    def get_relation_database_id(self,property):
        return property.get('relation').get("database_id")
    def write_database_id(self, database_id):
        env_file = os.getenv('GITHUB_ENV')
        # 将值写入环境文件
        with open(env_file, "a") as file:
            file.write(f"DATABASE_ID={database_id}\n")
    def extract_page_id(self, notion_url):
        # 正则表达式匹配 32 个字符的 Notion page_id
        match = re.search(
            r"([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
            notion_url,
        )
        if match:
            return match.group(0)
        else:
            raise Exception(f"获取NotionID失败，请检查输入的Url是否正确")

    def search_database(self, block_id):
        children = self.client.blocks.children.list(block_id=block_id)["results"]
        # 遍历子块
        for child in children:
            # 检查子块的类型

            if child["type"] == "child_database":
                self.database_id_dict[child.get("child_database").get("title")] = (
                    child.get("id")
                )
            elif child["type"] == "embed" and child.get("embed").get("url"):
                url =    child.get("embed").get("url")
                if url.startswith("https://heatmap.malinkang.com/"):
                    if("/tomato/" in url):
                        self.tomato_heatmap_block_id = child.get("id")
                    else:
                        self.todo_heatmap_block_id = child.get("id")
            # 如果子块有子块，递归调用函数
            if "has_children" in child and child["has_children"]:
                self.search_database(child["id"])

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_heatmap(self, block_id, url):
        # 更新 image block 的链接
        return self.client.blocks.update(block_id=block_id, embed={"url": url})
    
    def get_week_relation_id(self, date):
        year = date.isocalendar().year
        week = date.isocalendar().week
        week = f"{year}年第{week}周"
        start, end = get_first_and_last_day_of_week(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            week, self.week_database_id, TARGET_ICON_URL, properties
        )

    def get_month_relation_id(self, date):
        month = date.strftime("%Y年%-m月")
        start, end = get_first_and_last_day_of_month(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            month, self.month_database_id, TARGET_ICON_URL, properties
        )

    def get_year_relation_id(self, date):
        year = date.strftime("%Y")
        start, end = get_first_and_last_day_of_year(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            year, self.year_database_id, TARGET_ICON_URL, properties
        )

    def get_day_relation_id(self, date):
        new_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day = new_date.strftime("%Y年%m月%d日")
        properties = {
            "日期": get_date(format_date(date)),
        }
        return self.get_relation_id(
            day, self.day_database_id, TARGET_ICON_URL, properties
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_relation_id(self, name, id, icon, properties={}):
        key = f"{id}{name}"
        if key in self.__cache:
            return self.__cache.get(key)
        filter = {"property": "标题", "title": {"equals": name}}
        response = self.client.databases.query(database_id=id, filter=filter)
        if len(response.get("results")) == 0:
            parent = {"database_id": id, "type": "database_id"}
            properties["标题"] = get_title(name)
            page_id = self.client.pages.create(
                parent=parent, properties=properties, icon=get_icon(icon)
            ).get("id")
        else:
            page_id = response.get("results")[0].get("id")
        self.__cache[key] = page_id
        return page_id

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_book_page(self, page_id, properties):
        return self.client.pages.update(page_id=page_id, properties=properties)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_page(self, page_id, properties,icon):
        return self.client.pages.update(page_id=page_id, properties=properties,icon=icon)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def create_page(self, parent, properties, icon):
        return self.client.pages.create(
            parent=parent, properties=properties, icon=icon
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query(self, **kwargs):
        kwargs = {k: v for k, v in kwargs.items() if v}
        return self.client.databases.query(**kwargs)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_block_children(self, id):
        results = []
        has_more = True
        start_cursor = None
        while has_more:
            response = self.client.blocks.children.list(id, start_cursor=start_cursor)
            results.extend(response.get("results"))
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more")
        return results

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def append_blocks(self, block_id, children):
        return self.client.blocks.children.append(block_id=block_id, children=children)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def append_blocks_after(self, block_id, children, after):
        return self.client.blocks.children.append(
            block_id=block_id, children=children, after=after
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def delete_block(self, block_id):
        return self.client.blocks.delete(block_id=block_id)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query_all_by_book(self, database_id, filter):
        results = []
        has_more = True
        start_cursor = None
        while has_more:
            response = self.client.databases.query(
                database_id=database_id,
                filter=filter,
                start_cursor=start_cursor,
                page_size=100,
            )
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more")
            results.extend(response.get("results"))
        return results

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query_all(self, database_id):
        """获取database中所有的数据"""
        results = []
        has_more = True
        start_cursor = None
        while has_more:
            response = self.client.databases.query(
                database_id=database_id,
                start_cursor=start_cursor,
                page_size=100,
            )
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more")
            results.extend(response.get("results"))
        return results
    
    def get_all_relation(self,properties):
        properties["全部"] = get_relation(
            [
                self.get_relation_id("全部",self.all_database_id,TARGET_ICON_URL),
            ]
        )

    def get_date_relation(self, properties, date):
        properties["年"] = get_relation(
            [
                self.get_year_relation_id(date),
            ]
        )
        properties["月"] = get_relation(
            [
                self.get_month_relation_id(date),
            ]
        )
        properties["周"] = get_relation(
            [
                self.get_week_relation_id(date),
            ]
        )
        properties["日"] = get_relation(
            [
                self.get_day_relation_id(date),
            ]
        )

