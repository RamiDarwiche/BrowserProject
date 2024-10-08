import socket
import ssl
import tkinter
import tkinter.font

# global constants
WIDTH, HEIGHT = 1200, 900
# horizontal and vertical steps are used for spacing printed text
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
FONTS = {}

# review logic
def get_font(size, weight, style):
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=style)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

def print_tree(node, indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

# URL class breaks down a standard http/https url into a format that enables browser access with a socket
class URL:
    # handle formatting
    def __init__(self, url):
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https"]

        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https": 
            self.port = 443

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def request(self):
        # initalize socket
        s = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        s.connect((self.host, self.port))
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
            
        request = "GET {} HTTP/1.0\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "\r\n"
        # use socket to send the request formatted above to the server
        s.send(request.encode("utf8"))

        # handle response from server, create an object converting bytes received from server to strings, statusline discarded
        response = s.makefile("r", encoding="utf8", newline="\r\n")
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        # raise error for unhandled special cases found in response headers
        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers
        
        # the remaining information received from the server is the visible content to be read by the end user
        content = response.read()
        s.close()
        
        return content


# text class for organizing strings within HTML tags
class Text:
    def __init__(self, text, parent):
        self.text = text
        self.children = []
        self.parent = parent
    
    def __repr__(self):
        return repr(self.text)


# tag class for enabling styling options in display
class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.attributes = attributes
        self.children = []
        self.parent = parent

    def __repr__(self):
        return "<" + self.tag + ">"

class HTMLParser:
    SELF_CLOSING_TAGS = ["area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr"]

    HEAD_TAGS = ["base", "basefont", "bgsound", "noscript",
    "link", "meta", "title", "style", "script",]

    def __init__(self, body):
        self.body = body
        self.unfinished = []

    # get keyword attributes within an html tag (ex. <a href="">)
    def get_attributes(self, text):
        parts = text.split()
        tag = parts[0].casefold()
        attributes = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                attributes[key.casefold()] = value
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]
            else:
                attributes[attrpair.casefold()] = ""
        return tag, attributes

    # parse through html tags
    def parse(self):
        text = ""
        in_tag = False
        for c in self.body:
            # look for opening tags
            if c == "<":
                in_tag = True
                if text: self.add_text(text)
                text = ""
            # look for closing tags
            elif c == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
            # append text within tag
            else:
                text += c
        # if character is text between opening and closing tags
        if not in_tag and text:
            self.add_text(text)
        return self.finish()
    
    # add body text between tags
    def add_text(self, text):
        if text.isspace(): return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    # add tag to html tree
    def add_tag(self, tag):
        tag, attributes = self.get_attributes(tag)
        # ignore !DOCTYPE
        if tag.startswith("!"): return
        self.implicit_tags(tag)

        if tag.startswith("/"):
            if len(self.unfinished) == 1: return
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    # complete html tree by parsing through unfinished tags
    def finish(self):
        if not self.unfinished:
            self.implicit_tags(None)
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()
    
    # add implicit tags to html to prevent bad html
    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
                self.add_tag("/head")
            else:
                break


class CSSParser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def whitespace(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1
        
    def word(self):
        start = self.i
        while self.i < len(self.s):
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%":
                self.i += 1
            else:
                break
        
        if not (self.i > start):
            raise Exception("Parsing error")
    
        return self.s[start:self.i]
    
    def literal(self, literal):
        if not (self.i < len(self.s) and self.s[self.i] == literal):
            raise Exception("Parsing error")
        self.i += 1

    def pair(self):
        prop = self.word()
        self.whitespace()
        self.literal(":")
        self.whitespace()
        val = self.word()

        return prop.casefold(), val
    
    def body(self):
        pairs = {}
        while self.i < len(self.s):
            try:
                prop, val = self.pair()
                pairs[prop.casefold()] = val
                self.whitespace()
                self.literal(":")
                self.whitespace()
            except Exception:
                why = self.ignore_until([";"])
                if why == ";":
                    self.literal(";")
                    self.whitespace()
                else:
                    break

        return pairs
    
    def ignore_until(self, chars):
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            else:
                self.i += 1
        
        return None
    

def style(node):
    node.style = {}
    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value

    for child in node.children:
        style(child)


# establishes the layout for text/words
# very similar to the html tree, but the layout tree is fundamentally different in the way it constructs blocks
# this is another tree structure that is derived from the html tree
class BlockLayout:

    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
        self.x = None
        self.y = None
        self.width = None
        self.height = None


    def layout(self):
        self.x = self.parent.x
        self.width = self.parent.width
        self.display_list = []
        mode = self.layout_mode()


        # if parent, start layout after parent, else, start layout at parent's top edge
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        
        if mode == "block":
            previous = None
            for child in self.node.children:
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next


        else:
            self.line = []        
            self.cursor_x = 0
            self.cursor_y = 0
            self.weight = "normal"
            self.style = "roman"
            self.size = 12
            self.recurse(self.node)
            self.flush()
            self.height = self.cursor_y # if no children read height from text height 

        for child in self.children:
            child.layout()

        if mode == "block":
            self.height = sum([child.height for child in self.children]) # containing block should be tall enough to contain its children

    def layout_intermediate(self):
        previous = None
        for child in self.node.children:
            next = BlockLayout(child, self, previous)
            self.children.append(next)
            previous = next

    # organize layout objects into blocks or inline text styles
    def layout_mode(self):
        BLOCK_ELEMENTS = [
            "html", "body", "article", "section", "nav", "aside",
            "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header",
            "footer", "address", "p", "hr", "pre", "blockquote",
            "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure",
            "figcaption", "main", "div", "table", "form", "fieldset",
            "legend", "details", "summary"]

        if isinstance(self.node, Text):
            return "inline"
        elif any([isinstance(child, Element) and child.tag in BLOCK_ELEMENTS for child in self.node.children]):
            return "block"
        elif self.node.children:
            return "inline"
        else:
            return "block"

    # define font styling changes dependent on some given tags
    def open_tag(self, tag):
        if tag == "i":
            self.style = "italic"
        elif tag == "b":
            self.weight = "bold"
        elif tag == "small":
            self.size -= 2
        elif tag == "big":
            self.size += 4
        elif tag == "br":
            self.flush()
        # elif "h1" in tag:
        #     self.size += 8

    def close_tag(self, tag):
        if tag == "i":
            self.style = "roman"
        elif tag =="b":
            self.weight = "normal"
        elif tag == "small":
            self.size += 2
        elif tag =="big":
            self.size -= 4
        elif tag =="p":
            self.flush()
            self.cursor_y += VSTEP  
        # elif tag == "h1":
        #     self.size -= 8
        #     self.flush()
        #     self.cursor_y += VSTEP*2

    def recurse(self, tree):
        if isinstance(tree, Text):
            for word in tree.text.split():
                self.word(word)
        else:
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)        

    def word(self, word):
        font = get_font(self.size, self.weight, self.style)
        w = font.measure(word)

        # wraps text for words that are too long to occupy a given line 
        if self.cursor_x + w > self.width:
            self.flush()
                       
        self.line.append((self.cursor_x, word, font))
        self.cursor_x += w + font.measure(" ")
        
    # function to properly align the baseline of text regardless of font differences
    def flush(self):
        if not self.line: return
        metrics = [font.metrics() for x, word, font, in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.cursor_y + 1.25 * max_ascent

        # positions text relative to containing block
        for rel_x, word, font in self.line:
            x = self.x + rel_x
            y = self.y + baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))

        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent

        self.cursor_x = 0
        self.line = []

    def paint(self):
        cmds = []
        if isinstance(self.node, Element) and self.node.tag == "pre":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, "gray")
            cmds.append(rect)
            
        if self.layout_mode() == "inline":
            for x, y, word, font in self.display_list:
                cmds.append(DrawText(x, y, word, font))

        # move this?
        bgcolor = self.node.style.get("background-color", "transparent")

        if bgcolor != "transparent":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
            cmds.append(rect)

        return cmds

    # to be implemented, align header text center
    def header_center(self):
        pass

# used for constructing the layout object that serves as the root of the layout tree
class DocumentLayout:
    def __init__(self, node):
        self.node = node
        self.parent = None
        self.children = []
        self.x = None
        self.y = None
        self.width = None
        self.height = None


    def layout(self):
        child = BlockLayout(self.node, self, None)
        self.children.append(child)

        self.width = WIDTH - 2*HSTEP
        self.x = HSTEP
        self.y = VSTEP
        child.layout()
        self.height = child.height

    def paint(self):
        return []


def paint_tree( layout_object, display_list):
    display_list.extend(layout_object.paint())

    for child in layout_object.children:
        paint_tree(child, display_list)
    
class DrawText:
    def __init__(self, x1, y1, text, font):
        self.top = y1
        self.left = x1
        self.text = text
        self.font = font
        self.bottom = y1+font.metrics("linespace")

    def execute(self, scroll, canvas):
        canvas.create_text(self.left, self.top - scroll,
                           text = self.text,
                           font = self.font,
                           anchor = 'nw')

class DrawRect:
    def __init__(self, x1, y1, x2, y2, color):
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color

    def execute(self, scroll, canvas):
        canvas.create_rectangle(self.left, self.top - scroll,
                                self.right, self.bottom - scroll,
                                width = 0,
                                fill=self.color)


class Browser:
    # create the browser window object and enable scrolling
    def __init__(self):
        self.window = tkinter.Tk(className="Browser")
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        # self.canvas.configure(bg='black')
        self.canvas.pack()
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)

    # load a given URL and initialize its contents to the browser window
    def load(self, url):
        body = url.request()
        self.nodes = HTMLParser(body).parse() # initialize layout tree
        self.nodes.style()
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)
        self.draw()
        # for debugging
        # print_tree(self.nodes)


    # function to draw the text of a webpage's body, text is appropriately redrawn to permit scrolling functionality 
    def draw(self):
        self.canvas.delete("all")
        for cmd in self.display_list:
            if cmd.top > self.scroll + HEIGHT: continue
            if cmd.bottom < self.scroll: continue
            cmd.execute(self.scroll, self.canvas)

    # scrolling functions
    def scrolldown(self, e):
        max_y = max(self.document.height + 2*VSTEP - HEIGHT, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)
        self.draw()

    def scrollup(self, e):
        if self.scroll != 0:
            self.scroll -= SCROLL_STEP
        self.draw()
    



if __name__ == "__main__":
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()