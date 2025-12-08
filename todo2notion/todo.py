#!/usr/bin/python
# -*- coding: UTF-8 -*-
import argparse
import json
import math
import mimetypes
import os
import time
from urllib.parse import unquote, urlparse

import pendulum
from todo2notion.notion_helper import NotionHelper, TAG_ICON_URL
import mistletoe
from todo2notion.notion_renderer import NotionPyRenderer
import requests
from dotenv import load_dotenv

from todo2notion import utils

load_dotenv()


headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "hl": "zh_CN",
    "origin": "https://dida365.com",
    "priority": "u=1, i",
    "referer": "https://dida365.com/",
    "sec-ch-ua": '"Chromium";v="141", "Google Chrome";v="141", "Not?A_Brand";v="8"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "traceid": "6721a893b8de3a0431a1548c",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "x-csrftoken": "GpesKselqEa9oKJQRM3bj8tkdT2kJVNSNaZ9eM0i3Q-1730258339",
    "x-device": '{"platform":"web","os":"macOS 10.15.7","device":"Chrome 141.0.0.0","name":"","version":6101,"id":"689e9fa68d521b4a0abec2cb","channel":"website","campaign":"","websocket":""}',
    "x-tz": "Asia/Shanghai",
    "cookie":os.getenv("COOKIE")
}


def is_task_modified(item, todo_dict):
    id = item.get("id")
    if item.get("modifiedTime") is None:
        return True
    modified_time = utils.parse_date(item.get("modifiedTime"))
    todo = todo_dict.get(id)
    if todo:
        last_modified_time = utils.get_property_value(
            todo.get("properties").get("最后修改时间")
        )
        # 判断笔记是否需要同步
        j = utils.get_property_value(todo.get("properties").get("笔记最后修改时间"))
        notes = utils.get_property_value(todo.get("properties").get("笔记"))
        if notes:
            if j:
                note_modification_dict = json.loads(j)
                for note in notes:
                    if note.get("id") not in note_modification_dict:
                        print(note.get("id"))
                        return True
                    note_page = notion_helper.client.pages.retrieve(note.get("id"))
                    last_edited_time = note_page.get("last_edited_time")
                    value = note_modification_dict.get(note.get("id"))
                    if last_edited_time != value:
                        return True
            else:
                return True
        if last_modified_time == modified_time:
            return False
    return True


def is_project_modified(item, project_dict):
    """根据最后修改时间判断是否被修改了"""
    id = item.get("id")
    if item.get("modifiedTime") is None:
        return True
    modified_time = utils.parse_date(item.get("modifiedTime"))
    project = project_dict.get(id)
    if project:
        last_modified_time = utils.get_property_value(
            project.get("properties").get("最后修改时间")
        )
        if last_modified_time == modified_time:
            return False
    return True


def get_projects(session, project_dict):
    """获取所有清单"""
    print("开始获取所有的project")
    start_time = time.time()
    r = session.get("https://api.dida365.com/api/v2/projects", headers=headers)
    utils.log_request_duration("获取所有的project", start_time)
    if r.ok:
        # 获取映射关系
        d = notion_helper.get_property_type(notion_helper.project_database_id)
        items = r.json()
        items = list(
            filter(lambda item: is_project_modified(item, project_dict), items)
        )
        for item in items:
            emoji, title = utils.split_emoji_from_string(item.get("name"))
            id = item.get("id")
            project = {
                "标题": title,
                "id": id,
                "最后修改时间": utils.parse_date(item.get("modifiedTime")),
            }
            icon = {"type": "emoji", "emoji": emoji}
            properties = utils.get_properties(project, d)
            if id in project_dict:
                notion_helper.update_page(
                    page_id=project_dict.get(id).get("id"),
                    properties=properties,
                    icon=icon,
                )
            else:
                parent = {
                    "database_id": notion_helper.project_database_id,
                    "type": "database_id",
                }
                result = notion_helper.create_page(
                    parent=parent, properties=properties, icon=icon
                )
                project_dict[id] = result
    else:
        print(f" Get projects failed ${r.text}")


def remove_duplicates(data):
    seen_ids = set()
    unique_data = []
    for item in data:
        if item["id"] not in seen_ids:
            unique_data.append(item)
            seen_ids.add(item["id"])
    return unique_data


def get_all_completed(session):
    """获取所有完成的任务"""
    print("开始获取所有完成的任务")
    start_time = time.time()
    date = pendulum.now()
    result = []
    while True:
        to = date.format("YYYY-MM-DD HH:mm:ss")
        r = session.get(
            f"https://api.dida365.com/api/v2/project/all/completedInAll/?from=&to={to}&limit=100",
            headers=headers,
        )
        if r.ok:
            l = r.json()
            if l:
                result.extend(l)
                completedTime = l[-1].get("completedTime")
                date = pendulum.parse(completedTime)
            if len(l) < 100:
                break
        else:
            print(f"获取任务失败 {r.text}")
    result = remove_duplicates(result)
    utils.log_request_duration("获取所有完成的任务", start_time)
    return result


def get_all_task(session):
    """获取所有未完成的任务"""
    print("开始获取所有未完成的任务")
    start_time = time.time()
    r = session.get("https://api.dida365.com/api/v2/batch/check/0", headers=headers)
    utils.log_request_duration("获取所有未完成的任务", start_time)
    results = []
    if r.ok:
        results.extend(r.json().get("syncTaskBean").get("update"))
    else:
        print(f"获取任务失败 {r.text}")
    return results


def get_task(session):
    """获取所有清单"""
    results = get_all_completed(session)
    results.extend(get_all_task(session))
    return results


def add_task_to_notion(items, project_dict, todo_dict, session, page_id=None):
    d = notion_helper.get_property_type(notion_helper.todo_database_id)
    items = list(filter(lambda item: is_task_modified(item, todo_dict), items))
    for index, item in enumerate(items):
        id = item.get("id")
        task = {"标题": item.get("title"), "id": id, "状态": "Not started"}
        if page_id:
            task["Parent task"] = [page_id]
        if item.get("projectId") and item.get("projectId") in project_dict:
            task["清单"] = [project_dict.get(item.get("projectId")).get("id")]
        if item.get("startDate"):
            task["开始时间"] = utils.parse_date(item.get("startDate"))
            task["time"] = item.get("startDate")
        if item.get("dueDate"):
            task["结束时间"] = utils.parse_date(item.get("dueDate"))
        if item.get("modifiedTime"):
            task["最后修改时间"] = utils.parse_date(item.get("modifiedTime"))
        if item.get("progress"):
            task["进度"] = item.get("progress") / 100
        persons = [
            x
            for x in notion_helper.client.users.list().get("results")
            if x.get("type") == "person"
        ]
        if persons:
            task["Assignee"] = persons
        if item.get("tags"):
            task["标签"] = [
                notion_helper.get_relation_id(
                    x, notion_helper.tag_database_id, TAG_ICON_URL
                )
                for x in item.get("tags")
            ]
        parent = {
            "database_id": notion_helper.todo_database_id,
            "type": "database_id",
        }
        icon = "https://www.notion.so/icons/circle_outline_green.svg"
        properties = {}
        if item.get("completedTime"):
            task["状态"] = "Done"
            task["完成时间"] = utils.parse_date(item.get("completedTime"))
            task["time"] = item.get("completedTime")
            icon = "https://www.notion.so/icons/checkmark_circle_green.svg"
        blocks = []
        if id in todo_dict:
            notes = utils.get_property_value(
                todo_dict.get(id).get("properties").get("笔记")
            )
            if notes:
                task["笔记"] = [x.get("id") for x in notes]
                note_modification_dict = {}
                for i in notes:
                    note_page = notion_helper.client.pages.retrieve(i.get("id"))
                    last_edited_time = note_page.get("last_edited_time")
                    note_modification_dict[i.get("id")] = last_edited_time
                task["笔记最后修改时间"] = json.dumps(
                    note_modification_dict, ensure_ascii=False
                )

            for note in notes:
                blocks.extend(notion_helper.get_block_children(note.get("id")))
            notion_helper.delete_block(todo_dict.get(id).get("id"))
        properties = {}
        notion_helper.get_all_relation(properties)
        if task.get("time"):
            chinese_weekdays = [
                "星期一",
                "星期二",
                "星期三",
                "星期四",
                "星期五",
                "星期六",
                "星期日",
            ]
            date = pendulum.parse(task.get("time"))
            date = date.in_timezone("Asia/Shanghai")
            chinese_day_of_week = chinese_weekdays[date.day_of_week]
            task["星期"] = chinese_day_of_week
            notion_helper.get_date_relation(properties, date)
        properties.update(utils.get_properties(task, d))
        result = notion_helper.create_page(
            parent=parent, properties=properties, icon=utils.get_icon(icon)
        )
        todo_dict[id] = result
        if item.get("content"):
            blocks = (
                convert_to_block(id, item.get("projectId"), item.get("content"),session)
                + blocks
            )
        if blocks:
            append_block(result.get("id"), blocks)
        if item.get("items"):
            add_task_to_notion(item.get("items"),project_dict, todo_dict, session, result.get("id"))


def convert_to_block(id, project_id, content, session):
    action = "Markdown转换为Notion block"
    print(f"开始{action}")
    start_time = time.time()
    blocks = []
    try:
        response = requests.post(
            "http://127.0.0.1:8787",
            data=content.encode("utf-8"),
            headers={"content-type": "text/markdown"},
            timeout=30,
        )
        if response.ok:
            blocks = response.json()
        else:
            print(f"{action}失败，状态码: {response.status_code}, 内容: {response.text}")
    except Exception as exc:
        print(f"{action}异常: {exc}")
    utils.log_request_duration(action, start_time)
    if not blocks:
        blocks = mistletoe.markdown(content, NotionPyRenderer)

    def upload_file_to_notion(file_name, file_content, content_type):
        file_size = len(file_content)
        if file_size == 0:
            print("文件内容为空，跳过上传")
            return None
        try:
            if file_size <= 20 * 1024 * 1024:
                response = notion_helper.client.file_uploads.create(
                    mode="simple",
                    filename=file_name,
                    content_type=content_type,
                )
                file_upload_id = response.get("id")
                notion_helper.client.file_uploads.send(
                    file_upload_id=file_upload_id,
                    file=(file_name, file_content, content_type),
                )
            else:
                part_size = 10 * 1024 * 1024
                number_of_parts = math.ceil(file_size / part_size)
                response = notion_helper.client.file_uploads.create(
                    mode="multi_part",
                    filename=file_name,
                    content_type=content_type,
                    number_of_parts=number_of_parts,
                )
                file_upload_id = response.get("id")
                for part_index in range(number_of_parts):
                    start = part_index * part_size
                    end = start + part_size
                    chunk = file_content[start:end]
                    notion_helper.client.file_uploads.send(
                        file_upload_id=file_upload_id,
                        file=(file_name, chunk, content_type),
                        part_number=str(part_index + 1),
                    )

            complete_response = notion_helper.client.file_uploads.complete(
                file_upload_id=file_upload_id
            )
            if complete_response.get("status") != "uploaded":
                print(f"文件上传Notion失败，状态：{complete_response.get('status')}")
                return None
            return file_upload_id
        except Exception as exc:
            print(f"上传到Notion失败: {exc}")
            return None

    def process_image_blocks(block_list):
        for block in block_list:
            if block.get("type") == "image":
                url = block.get("image", {}).get("external", {}).get("url")
                if not url:
                    continue
                parsed_url = urlparse(url)
                paths = unquote(parsed_url.path).strip("/").split("/")
                if len(paths) < 2:
                    continue
                dir_name = paths[-2]
                file_name = paths[-1]
                download_url = f"https://api.dida365.com/api/v1/attachment/{project_id}/{id}/{dir_name}?action=download"
                action_download = f"下载图片 {download_url}"
                print(f"开始{action_download}")
                download_start_time = time.time()
                response = session.get(download_url, headers=headers)
                utils.log_request_duration(action_download, download_start_time)
                if response.status_code == 200:
                    content_type = (
                        response.headers.get("Content-Type")
                        or mimetypes.guess_type(file_name)[0]
                        or "application/octet-stream"
                    )
                    file_upload_id = upload_file_to_notion(
                        file_name, response.content, content_type
                    )
                    if file_upload_id:
                        image_block = {
                            "type": "file_upload",
                            "file_upload": {"id": file_upload_id},
                        }
                        caption = block.get("image", {}).get("caption")
                        if caption:
                            image_block["caption"] = caption
                        block["image"] = image_block
                else:
                    print(f"文件下载失败，状态码: {response.status_code}")
            # 递归处理子块中的图片
            if block.get("children"):
                process_image_blocks(block.get("children"))

    process_image_blocks(blocks)
    return blocks



def append_block(block_id, blocks):
    for block in blocks:
        children = None
        if block.get("children"):
            children = block.pop("children")
        id = (
            notion_helper.client.blocks.children.append(
                block_id=block_id, children=[block]
            )
            .get("results")[0]
            .get("id")
        )
        if children:
            append_block(id, children)


def main():
    session = requests.Session()
    projects = notion_helper.query_all(notion_helper.project_database_id)
    project_dict = {}
    for item in projects:
        project_dict[utils.get_property_value(item.get("properties").get("id"))] = item
    get_projects(session, project_dict)
    todos = notion_helper.query_all(notion_helper.todo_database_id)
    todo_dict = {}
    for todo in todos:
        todo_dict[utils.get_property_value(todo.get("properties").get("id"))] = todo
    tasks = get_task(session)
    add_task_to_notion(tasks,project_dict,todo_dict,session)


notion_helper = NotionHelper()
if __name__ == "__main__":
    main()
