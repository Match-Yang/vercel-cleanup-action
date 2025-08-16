#!/usr/bin/env python3
"""
Vercel 部署清理脚本

此脚本用于删除所有处于 Queued 和 Building 状态的 Vercel 部署。
支持多项目配置，可以同时清理多个项目的部署。
"""

import os
import sys
import subprocess
import re
import time
import json
from typing import List, Tuple, Optional


def log_info(message: str):
    """输出信息日志"""
    print(f"ℹ️  {message}")


def log_success(message: str):
    """输出成功日志"""
    print(f"✅ {message}")


def log_warning(message: str):
    """输出警告日志"""
    print(f"⚠️  {message}")


def log_error(message: str):
    """输出错误日志"""
    print(f"❌ {message}")


def check_vercel_cli() -> bool:
    """检查 Vercel CLI 是否已安装"""
    try:
        result = subprocess.run(['vercel', '--version'],
                              capture_output=True, text=True, check=False)
        if result.returncode == 0:
            log_info(f"Vercel CLI 版本: {result.stdout.strip()}")
            return True
        else:
            return False
    except FileNotFoundError:
        return False


def get_project_list() -> List[str]:
    """获取要处理的项目列表"""
    # 优先使用工作流输入的项目列表
    input_projects = os.getenv('INPUT_PROJECTS', '').strip()
    if input_projects:
        projects = [p.strip() for p in input_projects.split(',') if p.strip()]
        log_info(f"使用工作流输入的项目列表: {projects}")
        return projects

    # 使用默认项目列表
    default_projects = os.getenv('DEFAULT_PROJECTS', '').strip()
    if default_projects:
        projects = [p.strip() for p in default_projects.split(',') if p.strip()]
        log_info(f"使用默认项目列表: {projects}")
        return projects

    # 如果都没有配置，返回空列表
    log_warning("没有配置任何项目，请在工作流文件中设置 DEFAULT_PROJECTS 或通过手动触发提供项目列表")
    return []


def list_deployments(project: str, token: str) -> Optional[str]:
    """列出指定项目的部署"""
    try:
        # 尝试不同的命令参数组合
        commands_to_try = [
            ['vercel', 'list', project, '--token', token],
            ['vercel', 'ls', project, '--token', token],
            ['vercel', 'deployments', 'list', project, '--token', token],
        ]

        for i, cmd in enumerate(commands_to_try):
            log_info(f"🚀 尝试命令 {i+1}: {' '.join(cmd[:3])} [项目名] --token [隐藏]")

            # 尝试不同的环境和缓冲设置
            env = os.environ.copy()
            env['FORCE_COLOR'] = '0'  # 禁用颜色输出
            env['NO_COLOR'] = '1'

            # 尝试不同的执行方式
            execution_methods = [
                # 方法1: 标准方式
                {'capture_output': True, 'text': True, 'shell': False},
                # 方法2: 使用 shell
                {'capture_output': True, 'text': True, 'shell': True},
                # 方法3: 不缓冲输出
                {'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'text': True, 'shell': False, 'bufsize': 0},
            ]

            result = None
            for method_idx, method_kwargs in enumerate(execution_methods):
                try:
                    log_info(f"   尝试执行方法 {method_idx + 1}")

                    if method_kwargs.get('shell'):
                        # 对于 shell=True，需要将命令转换为字符串
                        shell_cmd = ' '.join([f'"{part}"' if ' ' in part else part for part in cmd])
                        result = subprocess.run(
                            shell_cmd,
                            timeout=30,
                            env=env,
                            universal_newlines=True,
                            **{k: v for k, v in method_kwargs.items() if k != 'shell'}
                        )
                    else:
                        result = subprocess.run(
                            cmd,
                            timeout=30,
                            env=env,
                            universal_newlines=True,
                            **method_kwargs
                        )

                    log_info(f"   方法 {method_idx + 1} 执行成功")
                    break

                except Exception as method_error:
                    log_info(f"   方法 {method_idx + 1} 失败: {method_error}")
                    continue

            if result is None:
                log_error(f"所有执行方法都失败了")
                continue

            log_info(f"📋 命令 {i+1} 返回码: {result.returncode}")

            # 打印完整的原始输出用于调试
            verbose = os.getenv('VERCEL_CLEANUP_VERBOSE', 'false').lower() in ['1', 'true', 'yes']
            if result.stdout:
                log_info(f"📤 标准输出长度: {len(result.stdout)} 字符")
                if verbose:
                    log_info("🔍 完整标准输出内容:")
                    stdout_lines = result.stdout.split('\n')
                    for j, line in enumerate(stdout_lines):
                        log_info(f"   stdout[{j:02d}]: {repr(line)}")
                else:
                    head = '\n'.join(result.stdout.split('\n')[:3])
                    if head:
                        log_info(f"   stdout 预览: {repr(head)} … (更多请设 VERCEL_CLEANUP_VERBOSE=true)")

            if result.stderr:
                log_info(f"⚠️  标准错误输出长度: {len(result.stderr)} 字符")
                if verbose:
                    log_info("🔍 完整错误输出内容:")
                    stderr_lines = result.stderr.split('\n')
                    for j, line in enumerate(stderr_lines):
                        if line.strip():  # 只显示非空行
                            log_info(f"   stderr[{j:02d}]: {repr(line)}")
                else:
                    head = '\n'.join([l for l in result.stderr.split('\n') if l.strip()][:3])
                    if head:
                        log_info(f"   stderr 预览: {repr(head)} … (更多请设 VERCEL_CLEANUP_VERBOSE=true)")

            # 合并 stdout 和 stderr，因为有些工具会将表格输出到 stderr
            combined_output = ""
            if result.stdout:
                combined_output += result.stdout
            if result.stderr:
                combined_output += "\n" + result.stderr

            if combined_output.strip():
                log_success(f"✅ 获取部署列表成功")
                return combined_output
            else:
                log_warning(f"⚠️  命令 {i+1} 没有输出内容")

        log_error(f"❌ 所有命令都无法获取项目 {project} 的有效输出")
        return None

    except subprocess.TimeoutExpired:
        log_error(f"获取项目 {project} 的部署列表超时")
        return None
    except Exception as e:
        log_error(f"获取项目 {project} 的部署列表时发生异常: {e}")
        return None


def parse_deployments(output: str) -> List[Tuple[str, str]]:
    """
    解析 vercel list 的输出，提取处于 Building 和 Queued 状态的部署
    返回 (deployment_url, status) 的列表
    """
    deployments = []
    lines = output.split('\n')

    log_info("🔍 开始解析 vercel list 输出...")
    log_info(f"📄 原始输出共 {len(lines)} 行")

    # 根据环境变量控制是否打印原始输出
    verbose = os.getenv('VERCEL_CLEANUP_VERBOSE', 'false').lower() in ['1', 'true', 'yes']
    if verbose:
        log_info("📋 原始输出内容:")
        for i, line in enumerate(lines):
            if line.strip():
                log_info(f"第{i+1:02d}行: {repr(line)}")

    # 查找部署列表的开始（跳过标题行）
    start_parsing = False
    header_found = False
    parse_count = 0
    MAX_PARSE_ROWS = 10

    for i, line in enumerate(lines):
        original_line = line
        line = line.strip()
        if not line:
            continue

        # 查找表头（多种可能的格式）
        if not header_found and ('Age' in line or 'Deployment' in line or 'Status' in line or 'Environment' in line or 'Duration' in line):
            log_info(f"✅ 找到表头行(第{i+1}行): {repr(original_line)}")
            header_found = True
            start_parsing = True
            continue

        # 如果还没找到表头，继续寻找
        if not start_parsing:
            continue

        # 尝试多种解析模式（最多处理前 10 行数据行，避免日志噪声与无谓开销）
        log_info(f"🔎 尝试解析行: {repr(original_line)}")
        parse_count += 1
        if parse_count > MAX_PARSE_ROWS:
            log_info("⏭️  已解析前 10 行数据，后续行跳过")
            break

        # 多种解析模式，涵盖不同的输出格式
        patterns = [
            # 匹配带 ● 符号的状态
            r'^\s*\S+\s+(https://[^\s]+)\s+●\s*(Building|Queued|building|queued)',
            # 匹配不带 ● 符号的状态
            r'^\s*\S+\s+(https://[^\s]+)\s+(Building|Queued|building|queued)',
            # 更宽松的匹配
            r'(https://[^\s]+).*?\s+(Building|Queued|building|queued)',
            # 匹配任何包含URL和状态的行
            r'(https://[^\s]+).*?(Building|Queued|building|queued)',
            # 匹配部分单词（如果状态被截断）
            r'(https://[^\s]+).*?\s+(Build|Queue|build|queue)',
        ]

        matched = False
        for pattern_idx, pattern in enumerate(patterns):
            match = re.search(pattern, original_line, re.IGNORECASE)
            if match:
                deployment_url = match.group(1)
                status = match.group(2)
                deployments.append((deployment_url, status))
                log_success(f"✨ 模式{pattern_idx+1}匹配成功: {deployment_url} (状态: {status})")
                matched = True
                break

        if not matched:
            log_info(f"⚪ 该行不匹配任何模式: {repr(original_line)}")

    if not header_found:
        log_warning("⚠️  未找到表头，可能输出格式发生变化")
        log_info("🔄 启用备用解析策略，尝试解析所有行（最多前 10 行）...")

        # 备用策略：解析所有行，不依赖表头
        parse_count = 0
        for i, original_line in enumerate(lines):
            if parse_count >= 10:
                log_info("⏭️  备用策略已解析前 10 行，后续行跳过")
                break
            line = original_line.strip()
            if not line or line.startswith('>') or line.startswith('You can learn more'):
                continue

            log_info(f"🔍 备用策略解析第{i+1}行: {repr(original_line)}")

            # 如果行中包含 https URL，尝试各种解析模式
            if 'https://' in original_line:
                patterns = [
                    # 尝试从完整表格行解析
                    r'(https://[^\s]+).*?●\s*(Building|Queued|building|queued)',
                    r'(https://[^\s]+).*?(Building|Queued|building|queued)',
                    # 如果只有URL，假设相邻行可能包含状态
                    r'^(https://[^\s]+)',
                ]

                matched = False
                for pattern_idx, pattern in enumerate(patterns):
                    match = re.search(pattern, original_line, re.IGNORECASE)
                    if match:
                        if len(match.groups()) >= 2:  # 包含状态
                            deployment_url = match.group(1)
                            status = match.group(2)
                            deployments.append((deployment_url, status))
                            log_success(f"✨ 备用模式{pattern_idx+1}匹配成功: {deployment_url} (状态: {status})")
                            matched = True
                            break
                        else:  # 只有 URL，查看前后行寻找状态
                            deployment_url = match.group(1)
                            log_info(f"🔗 找到 URL: {deployment_url}，查找状态...")

                            # 查看前后几行寻找 Building 或 Queued 状态
                            search_range = range(max(0, i-2), min(len(lines), i+3))
                            for j in search_range:
                                if i == j:
                                    continue
                                search_line = lines[j].strip()
                                if re.search(r'\b(Building|Queued|building|queued)\b', search_line, re.IGNORECASE):
                                    status_match = re.search(r'\b(Building|Queued|building|queued)\b', search_line, re.IGNORECASE)
                                    if status_match:
                                        status = status_match.group(1)
                                        deployments.append((deployment_url, status))
                                        log_success(f"✨ 在第{j+1}行找到状态: {deployment_url} (状态: {status})")
                                        matched = True
                                        break

                            if matched:
                                break

                if not matched:
                    log_info(f"⚪ 该行未匹配: {repr(original_line)}")

    # 最激进的备用策略：如果我们只收到了 URL 列表，但没有状态信息
    if len(deployments) == 0 and len([l for l in lines if 'https://' in l and l.strip()]) >= 3:
        log_warning("🚨 启用最激进备用策略：基于 URL 模式推测状态（最多取前 3 个）")
        log_warning("⚠️  注意：此策略存在风险，可能误删除部署")

        url_lines = [l.strip() for l in lines if 'https://' in l and l.strip()]
        log_info(f"📋 找到 {len(url_lines)} 个 URL")

        # 假设最新的几个部署（前3个）可能处于 Building/Queued 状态
        for i, url_line in enumerate(url_lines[:3]):  # 只处理前3个
            if 'https://' in url_line:
                url_match = re.search(r'(https://[^\s]+)', url_line)
                if url_match:
                    deployment_url = url_match.group(1)
                    # 推测状态：第一个可能是 Building，其他可能是 Queued
                    assumed_status = "Building" if i == 0 else "Queued"

                    log_warning(f"🤔 推测部署 {deployment_url} 状态为: {assumed_status}")
                    log_warning(f"   (基于您终端输出中显示的前{i+1}个部署)")

                    # 询问用户确认（通过环境变量）
                    auto_confirm = os.getenv('AUTO_CONFIRM_AGGRESSIVE_CLEANUP', '').lower() in ['true', '1', 'yes']
                    if auto_confirm:
                        deployments.append((deployment_url, assumed_status))
                        log_warning(f"🤖 自动确认删除: {deployment_url} (状态: {assumed_status})")
                    else:
                        log_warning(f"🛑 跳过推测删除（需要设置 AUTO_CONFIRM_AGGRESSIVE_CLEANUP=true 环境变量来启用）")

        if len(deployments) > 0:
            log_warning(f"⚡ 激进策略找到 {len(deployments)} 个待删除部署")

    log_info(f"📊 解析完成，找到 {len(deployments)} 个待删除部署")
    return deployments




def delete_deployment(deployment_url: str, token: str) -> bool:
    """删除指定的部署"""
    try:
        cmd = ['vercel', 'rm', deployment_url, '--token', token, '-y']
        log_info(f"🗑️  执行删除命令: vercel rm [URL] --token [隐藏] -y")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        log_info(f"📋 删除命令返回码: {result.returncode}")
        if result.stdout:
            log_info(f"📤 删除命令标准输出: {result.stdout.strip()}")
        if result.stderr:
            log_info(f"⚠️  删除命令错误输出: {result.stderr.strip()}")

        if result.returncode == 0:
            log_success(f"✅ 成功删除部署: {deployment_url}")
            return True
        else:
            log_error(f"❌ 删除部署失败 {deployment_url}")
            log_error(f"   返回码: {result.returncode}")
            log_error(f"   错误信息: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        log_error(f"⏰ 删除部署 {deployment_url} 超时（60秒）")
        return False
    except Exception as e:
        log_error(f"💥 删除部署 {deployment_url} 时发生异常: {e}")
        return False


def cleanup_project_deployments(project: str, token: str) -> Tuple[int, int]:
    """
    清理单个项目的部署
    返回 (成功删除数量, 总尝试删除数量)
    """
    log_info("=" * 60)
    log_info(f"🎯 开始处理项目: {project}")

    # 策略说明：保留最新 1 条（列表第 1 个），删除其余
    log_info("策略：保留最新 1 条 Building/Queued 部署，删除其余")

    # 获取部署列表
    output = list_deployments(project, token)
    if not output:
        log_warning(f"❌ 无法获取项目 {project} 的部署列表")
        return 0, 0

    log_info(f"✅ 成功获取项目 {project} 的部署列表")

    # 解析待删除的部署
    deployments = parse_deployments(output)

    if not deployments:
        log_info(f"✨ 项目 {project} 没有需要清理的部署（Building/Queued 状态）")
        return 0, 0

    log_info(f"🎯 项目 {project} 找到 {len(deployments)} 个待删除部署")
    for i, (url, status) in enumerate(deployments, 1):
        log_info(f"  {i}. {url} (状态: {status})")

    # 简化策略：始终保留最新 1 条（列表第 1 个），删除其余
    success_count = 0
    attempted = 0

    for i, (deployment_url, status) in enumerate(deployments, 1):
        if i == 1:
            log_info(f"⏭️  跳过删除（保留最新一条）: {deployment_url} ({status})")
            continue

        attempted += 1
        log_info(f"🗑️  [{attempted}/{max(len(deployments)-1, 0)}] 正在删除 {status} 状态的部署: {deployment_url}")
        if delete_deployment(deployment_url, token):
            success_count += 1
        else:
            log_error(f"❌ 删除失败: {deployment_url}")

        # 稍微延迟一下，避免API限制
        if i < len(deployments):  # 最后一个不需要延迟
            log_info("⏱️  等待1秒以避免API限制…")
            time.sleep(1)

    log_success(f"🎉 项目 {project} 处理完成: 成功删除 {success_count}/{attempted} 个部署（共发现 {len(deployments)} 个待处理，跳过 {len(deployments)-attempted} 个）")
    return success_count, attempted


def main():
    """主函数"""
    log_info("🚀 开始 Vercel 部署清理脚本")
    log_info("=" * 60)

    # 打印环境信息
    log_info("🔧 环境信息:")
    log_info(f"  Python 版本: {sys.version}")
    log_info(f"  操作系统: {os.uname() if hasattr(os, 'uname') else '未知'}")
    log_info(f"  当前工作目录: {os.getcwd()}")

    # 打印环境变量状态
    log_info("🔑 环境变量状态:")
    log_info(f"  VERCEL_CLI_TOKEN: {'✅ 已设置' if os.getenv('VERCEL_CLI_TOKEN') else '❌ 未设置'}")
    log_info(f"  DEFAULT_PROJECTS: '{os.getenv('DEFAULT_PROJECTS', '')}'")
    log_info(f"  INPUT_PROJECTS: '{os.getenv('INPUT_PROJECTS', '')}'")

    # 检查 Vercel CLI
    log_info("🛠️  检查 Vercel CLI...")
    if not check_vercel_cli():
        log_error("❌ Vercel CLI 未安装或无法访问")
        sys.exit(1)

    # 检查 token
    token = os.getenv('VERCEL_CLI_TOKEN')
    if not token:
        log_error("❌ 未找到 VERCEL_CLI_TOKEN 环境变量")
        log_error("   请在 GitHub 仓库的 Secrets 中添加 VERCEL_CLI_TOKEN")
        sys.exit(1)

    log_success(f"✅ Token 已配置（长度: {len(token)} 字符）")

    # 获取项目列表
    projects = get_project_list()
    if not projects:
        log_warning("⚠️  没有配置任何项目，脚本将退出")
        log_warning("   请在工作流文件中设置 DEFAULT_PROJECTS 或通过手动触发提供项目列表")
        sys.exit(0)

    log_info(f"📋 将处理 {len(projects)} 个项目: {', '.join(projects)}")

    # 处理每个项目
    total_success = 0
    total_attempted = 0

    for i, project in enumerate(projects, 1):
        try:
            log_info(f"\n📍 [{i}/{len(projects)}] 处理项目: {project}")
            success, attempted = cleanup_project_deployments(project, token)
            total_success += success
            total_attempted += attempted
        except Exception as e:
            log_error(f"💥 处理项目 {project} 时发生未预期错误: {e}")
            import traceback
            log_error(f"   错误堆栈:\n{traceback.format_exc()}")
            continue

    # 输出总结
    log_info("\n" + "=" * 60)
    log_info("📊 最终统计:")
    log_info(f"  🎯 处理项目数量: {len(projects)}")
    log_info(f"  🔍 发现待删除部署: {total_attempted}")
    log_info(f"  ✅ 成功删除部署: {total_success}")
    log_info(f"  ❌ 删除失败部署: {total_attempted - total_success}")

    if total_attempted == 0:
        log_info("🎉 没有找到需要清理的部署，所有项目都很干净！")
    else:
        if total_success == total_attempted:
            log_success(f"🎉 完美！成功删除了所有 {total_success} 个待清理部署")
        else:
            log_warning(f"⚠️  部分删除失败：成功 {total_success}/{total_attempted}")

    if total_success < total_attempted:
        log_warning("🔍 请查看上面的详细日志了解失败原因")
        sys.exit(1)
    else:
        log_success("🏁 脚本执行完成！")
        sys.exit(0)


if __name__ == '__main__':
    main()
