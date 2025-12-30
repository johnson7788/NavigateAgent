import asyncio

async def translate_tool(doc_id: int) -> str:
    """
    根据论文的id查询论文的中文，这个函数需要改进
    todo：
    :param doc_id: 查询哪篇论文的正文内容
    :return: 返回论文的整篇内容
    """
    item ={}
    print(f"调用工具，PaperQuery收到的id: {doc_id}")
    paper_markdown = []
    if doc_id:
        markdown_content = f"论文翻译完成啦：此处模拟的内容，请根据你的需求进行调用对应的工具\n"
        paper_markdown.append(markdown_content)
    papers_content = "\n\n".join(paper_markdown)
    return papers_content


async def main():
    papers = await translate_tool(doc_id=40668760)
    print(f"papers: {papers}")


if __name__ == '__main__':
    asyncio.run(main())