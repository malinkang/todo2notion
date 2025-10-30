from itertools import chain
import random
import re
from collections.abc import Iterable
from mistletoe.base_renderer import BaseRenderer
from mistletoe.block_token import HTMLBlock, CodeFence
from mistletoe.span_token import Image, Link, HTMLSpan, SpanToken
from html.parser import HTMLParser


def flatten(l):
    for el in l:
        if isinstance(el, Iterable) and not isinstance(el, (str, bytes, dict)):
            yield from flatten(el)
        else:
            yield el


def addHtmlImgTagExtension(notionPyRendererCls):
    """A decorator that add the image tag extension to the argument list. The
    decorator pattern allows us to chain multiple extensions. For example, we
    can create a renderer with extension A, B, C by writing:
        addAExtension(addBExtension(addCExtension(notionPyRendererCls)))
    """

    def newNotionPyRendererCls(*extraExtensions):
        new_extension = [HTMLBlock, HTMLSpan]
        return notionPyRendererCls(*chain(new_extension, extraExtensions))

    return newNotionPyRendererCls


def addLatexExtension(notionPyRendererCls):
    """A decorator that add the latex extensions to the argument list.
    Markdown such as $equation$ is parsed as inline-equations and
    $$equation$$ is parsed as an equation block.
    """

    def newNotionPyRendererCls(*extraExtensions):
        new_extension = [BlockEquation, InlineEquation]
        return notionPyRendererCls(*chain(new_extension, extraExtensions))

    return newNotionPyRendererCls


class NotionPyRenderer(BaseRenderer):
    """
    A class that will render out a Markdown file into a descriptor for upload
    with notion-py. Each object will have a .type for the block type and then
    a bunch of different dict entries corresponding to kwargs for that block
    type.
    For CollectionViewBlocks, a .rows entry exists in the dictionary with a list
    object containing a descriptor for every row. This is still TODO
    """

    def __init__(self, *extraExtensions):
        """
        Args:
            *extraExtensions: a list of custom tokens to be added to the mistletoe parser.
        """
        super().__init__(*extraExtensions)

    def render(self, token):
        """
        Takes a single Markdown token and renders it down to
        NotionPy classes. Note that all the recursion is handled in the delegated
        methods.
        Overrides super().render but still uses render_map and then just
        does special parsing for stuff
        """
        return self.render_map[token.__class__.__name__](token)

    def renderMultiple(self, tokens):
        """
        Takes an array of sibling tokens and renders each one out.
        """
        return list(flatten(self.render(t) for t in tokens))

    def renderMultipleToString(self, tokens):
        """
        Takes tokens and render them to a single string (if possible). Anything it
        can't convert to a string will be returned in the second part of the tuple
        @param {objects} tokens
        @returns {tuple} (str, dict[])
        """

        blocks = self.renderMultiple(tokens)
        return blocks

    def renderMultipleToStringAndCombine(self, tokens, toBlockFunc):
        """
        renderMultipleToString but combines the string with the other blocks
        with the returned block from toBlockFunc
        @param {objects} tokens
        @param {function} toBlockFunc Takes a str and returns a dict for the created
        @returns {dict[]}
        """
        blocks = self.renderMultipleToString(tokens)
        ret = []
        for block in blocks:
            ret = ret + [toBlockFunc(block)]
        return ret

    def render_document(self, token):
        return self.renderMultiple(token.children)

    # == MD Block Tokens ==
    def render_block_code(self, token):
        # Indented code and ``` ``` code fence
        # Notion seems really picky about the language field and the case sensitivity
        # so we match the string to the specific version that Notion.so expects
        notionSoLangs = [
            "ABAP",
            "Arduino",
            "Bash",
            "BASIC",
            "C",
            "Clojure",
            "CoffeeScript",
            "C++",
            "C#",
            "CSS",
            "Dart",
            "Diff",
            "Docker",
            "Elixir",
            "Elm",
            "Erlang",
            "Flow",
            "Fortran",
            "F#",
            "Gherkin",
            "GLSL",
            "Go",
            "GraphQL",
            "Groovy",
            "Haskell",
            "HTML",
            "Java",
            "JavaScript",
            "JSON",
            "Kotlin",
            "LaTeX",
            "Less",
            "Lisp",
            "LiveScript",
            "Lua",
            "Makefile",
            "Markdown",
            "Markup",
            "MATLAB",
            "Nix",
            "Objective-C",
            "OCaml",
            "Pascal",
            "Perl",
            "PHP",
            "Plain Text",
            "PowerShell",
            "Prolog",
            "Python",
            "R",
            "Reason",
            "Ruby",
            "Rust",
            "Sass",
            "Scala",
            "Scheme",
            "Scss",
            "Shell",
            "SQL",
            "Swift",
            "TypeScript",
            "VB.Net",
            "Verilog",
            "VHDL",
            "Visual Basic",
            "WebAssembly",
            "XML",
            "YAML",
        ]
        if token.language != "":
            matchLang = next(
                (
                    lang
                    for lang in notionSoLangs
                    if re.match(re.escape(token.language), lang, re.I)
                ),
                "",
            )
            if not matchLang:
                print(
                    f"Code block language {token.language} has no corresponding syntax in Notion.so"
                )
        else:
            matchLang = "Plain Text"

        def blockFunc(blockStr):
            return {
                "type": "code",
                "code": {
                    "caption": [],
                    "rich_text": [blockStr],
                    "language": matchLang.lower(),
                },
            }

        return self.renderMultipleToStringAndCombine(token.children, blockFunc)

    def render_thematic_break(self, token):
        return {"type": "divider", "divider": {}}

    def render_heading(self, token):
        level = token.level
        if level > 3:
            print(f"h{level} not supported in Notion.so, converting to h3")
            level = 3

        def blockFunc(blockStr):
            type = ["heading_1", "heading_2", "heading_3"][level - 1]
            return {
                "type": type,
                type: {"rich_text": [blockStr]},
            }

        return self.renderMultipleToStringAndCombine(token.children, blockFunc)

    def render_quote(self, token):
        def blockFunc(blockStr):
            return {"type": "quote", "quote": blockStr.pop("paragraph")}

        return self.renderMultipleToStringAndCombine(token.children, blockFunc)

    def render_paragraph(self, token):
        def blockFunc(blockStr):
            if blockStr and blockStr.get("type") == "text":
                return {
                    "type": "paragraph",
                    "paragraph": {"rich_text": [blockStr]},
                }
            return blockStr

        result = self.renderMultipleToStringAndCombine(token.children, blockFunc)
        return result

    def render_list(self, token):
        # List items themselves are each blocks, so skip it and directly render
        # the children
        return self.renderMultiple(token.children)

    def render_list_item(self, token):
        # Lists can have "children" (nested lists, nested images...), so we need
        # to render out all the nodes and sort through them to find the string
        # for this item and any children
        rendered = self.renderMultiple(token.children)
        rich_text = []
        children = []
        for item in rendered:
            if item.get("type")=="paragraph":
                rich_text.extend(item.get("paragraph").get("rich_text"))
            else:
                children.append(item)
        if len(rendered) == 0:
            return None
        strings = [
            s["text"]["content"]
            for s in rendered[0]["paragraph"]["rich_text"]
            if s["type"] == "text"
        ]
        if re.match(r"\d", token.leader):  # Contains a number
            return {
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": rich_text},
            }
        strContent = "".join(strings)
        match = re.match(r"^\[([x ])\][ \t]", strContent, re.I)
        if match:
            rendered[0]["paragraph"]["rich_text"][0]["text"]["content"] = strContent[
                len(match.group(0)) :
            ]
            return {
                "type": "to_do",
                "to_do": {"rich_text": rich_text},
            }
        result = {
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rich_text},
        }
        if children:
            result["children"] = children
        return result

    def render_table(self, token):
        headerRow = self.render(token.header)  # Header is a single row
        rows = [
            self.render(r) for r in token.children
        ]  # don't use renderMultiple because it flattens

        def randColId():
            def randChr():
                # ASCII 32 - 126 is ' ' to '~', all printable characters
                return chr(random.randrange(32, 126))

            # 4 characters long of random printable characters, I don't think it
            # has any correlation to the data?
            return "".join([randChr() for c in range(4)])

        def textColSchema(colName):
            return {"name": colName, "type": "text"}

        # The schema is basically special identifiers + the type of property
        # to put into Notion. Coming from Markdown, everything is going to
        # be text.
        # 'J=}x': {
        #     'name': 'Column',
        #     'type': 'text'
        # },
        schema = {
            randColId(): textColSchema(headerRow[r]) for r in range(len(headerRow) - 1)
        }
        # The last one needs to be named 'Title' and is type title
        # 'title': {
        #     'name': 'Name',
        #     'type': 'title'
        # }
        schema.update({"title": {"name": headerRow[-1], "type": "title"}})

        # CollectionViewBlock, and it's gonna be a bit hard to do because this
        # isn't fully fleshed out in notion-py yet but we can still use create_record
        return {
            "type": CollectionViewBlock,
            "rows": rows,  # everything except the initial row
            "schema": schema,
        }

    def render_table_row(self, token):
        # Rows are a concept in Notion (`CollectionRowBlock`) but notion-py provides
        # another API to use it, `.add_row()` so we just render down to an array
        # and handle in the Table block.
        return self.renderMultiple(token.children)

    def render_table_cell(self, token):
        # Render straight down to a string, cells aren't a concept in Notion
        strs, blocks = self.renderMultipleToString(token.children)
        if blocks:
            print(
                "Table cell contained non-strings (maybe an image?) and could not add..."
            )
        return strs

    # == MD Span Tokens ==
    # These tokens always appear inside another block-level token (so we can return
    # a string instead of a block if necessary). Most of these are handled by
    # notion-py's uploader as it will convert them to the internal Notion.so
    # MD-like formatting
    def render_strong(self, token):
        def blockFunc(blockStr):
            blockStr["annotations"]["bold"] = True
            return blockStr

        return self.renderMultipleToStringAndCombine(token.children, blockFunc)

    def render_emphasis(self, token):
        def blockFunc(blockStr):
            blockStr["annotations"]["italic"] = True
            return blockStr

        return self.renderMultipleToStringAndCombine(token.children, blockFunc)

    def render_inline_code(self, token):
        def blockFunc(blockStr):
            blockStr["annotations"]["code"] = True
            return blockStr

        return self.renderMultipleToStringAndCombine(token.children, blockFunc)

    def render_raw_text(self, token):
        if token.content.startswith("~") and token.content.endswith("~"):
            return {
                "type": "text",
                "text": {"content": token.content[1:-1]},
                "annotations": {"underline": True},
            }
        return {"type": "text", "text": {"content": token.content}, "annotations": {}}

    def render_strikethrough(self, token):
        def blockFunc(blockStr):
            blockStr["annotations"]["strikethrough"] = True
            return blockStr

        return self.renderMultipleToStringAndCombine(token.children, blockFunc)

    def render_link(self, token):
        def blockFunc(blockStr):
            blockStr["text"]["link"] = {"url": token.target}
            return blockStr

        return self.renderMultipleToStringAndCombine(token.children, blockFunc)

    def render_escape_sequence(self, token):
        # Pretty sure this is just like \xxx type escape sequences?
        return self.renderMultipleToStringAndCombine(token.children, lambda s: f"\\{s}")

    def render_line_break(self, token):
        return {"type": "text", "text": {"content": ""}}

    def render_image(self, token):
        return {
            "object": "block",
            "type": "image",
            "image": {
                "type": "external",
                "external": {
                    "url": token.src
                },
            },
        }

    class __HTMLParser(HTMLParser):

        def __init__(self):
            super().__init__()
            self._images = []
            self._html = []

        def get_result(self):
            return ("".join(self._html), self._images)

        def handle_starttag(self, tag, attrs):
            if tag != "img":
                self._html.append(self.get_starttag_text())
                return

            src = next((value for key, value in attrs if key == "src"), "")
            alt = next((value for key, value in attrs if key == "alt"), None)
            image = {
                "type": ImageBlock,
                "display_source": src,
                "source": src,
                "caption": alt,
            }
            self._images.append(image)

        def handle_endtag(self, tag):
            if tag != "img":
                self._html.append(f"</{tag}>")

        def handle_data(self, data):
            self._html.append(data)

    def render_html(self, token):
        content = token.content
        parser = self.__HTMLParser()
        parser.feed(content)
        strippedContent, images = parser.get_result()

        ret = images
        if strippedContent.strip() != "":
            ret.insert(0, {"type": TextBlock, "title": strippedContent})
        return ret

    def render_html_block(self, token):
        assert not hasattr(token, "children")
        return self.render_html(token)

    def render_html_span(self, token):
        assert not hasattr(token, "children")
        return self.render_html(token)

    def render_block_equation(self, token):
        def blockFunc(blockStr):
            return {
                "type": EquationBlock,
                "title_plaintext": blockStr.replace("\\", "\\\\"),
            }

        return self.renderMultipleToStringAndCombine(token.children, blockFunc)

    def render_inline_equation(self, token):
        return self.renderMultipleToStringAndCombine(
            token.children, lambda s: f"$${s}$$"
        )


class InlineEquation(SpanToken):
    pattern = re.compile(
        r"(?<!\\|\$)(?:\\\\)*(\$+)(?!\$)(.+?)(?<!\$)\1(?!\$)", re.DOTALL
    )
    parse_inner = True
    parse_group = 2


class BlockEquation(CodeFence):
    pattern = re.compile(r"( {0,3})((?:\$){2,}) *(\S*)")
