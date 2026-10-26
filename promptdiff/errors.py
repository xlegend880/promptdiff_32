"""统一的异常类型。

CLI 层只需要捕获 PromptDiffError 及其子类，就能把所有可预期的失败
（用例集写错、模型接口报错、基线文件损坏）转换成稳定的退出码。
"""


class PromptDiffError(Exception):
    """所有可预期错误的基类。"""


class SuiteError(PromptDiffError):
    """用例集格式非法。"""


class ProviderError(PromptDiffError):
    """模型提供方调用失败。"""


class BaselineError(PromptDiffError):
    """基线结果文件缺失或损坏。"""
