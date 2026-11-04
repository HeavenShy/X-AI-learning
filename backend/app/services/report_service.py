from app.core.exceptions import BizError
from app.models.report import Report, ReportGenerateRequest


async def generate_report(req: ReportGenerateRequest) -> Report:
    # TODO: scoring_service 计算正确率 + app/llm/report_chain 生成复盘报告
    raise BizError(code=5001, message="复盘报告功能尚未实现")
