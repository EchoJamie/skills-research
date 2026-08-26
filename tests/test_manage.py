import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "manage.py"
SPEC = importlib.util.spec_from_file_location("skills_research_manage", SCRIPT)
manage = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = manage
SPEC.loader.exec_module(manage)


class ResourceManagerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.repo = root / "repo"
        self.codex = root / "codex"
        self.skills_home = root / "user-skills"
        self.agents_home = root / "user-agents"
        for relative in ("skills", "agents", "research"):
            (self.repo / relative).mkdir(parents=True, exist_ok=True)
        for relative in ("README.md", "AGENTS.md", ".gitignore"):
            (self.repo / relative).write_text("test\n", encoding="utf-8")

        skill = self.repo / "skills" / "demo-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\n"
            "name: demo-skill\n"
            "description: 用于验证资源管理器。\n"
            "---\n\n"
            "执行测试任务。\n",
            encoding="utf-8",
        )
        (self.repo / "agents" / "demo-agent.toml").write_text(
            'name = "demo_agent"\n'
            'description = "用于测试。"\n'
            'developer_instructions = "只执行测试任务。"\n',
            encoding="utf-8",
        )
        paths = manage.InstallPaths(
            skills_home=self.skills_home,
            agents_home=self.agents_home,
            state_home=self.codex / ".skills-research",
            codex_home=self.codex,
        )
        self.manager = manage.ResourceManager(self.repo, paths)

    def tearDown(self):
        self.temporary.cleanup()

    def add_installed_skill(self, name: str) -> Path:
        skill = self.repo / "installed" / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            "description: 用于验证正式已安装集合。\n"
            "---\n\n"
            "执行正式版本任务。\n",
            encoding="utf-8",
        )
        return skill

    def add_installed_agent(self, name: str, marker: str = "formal") -> Path:
        agent = self.repo / "installed" / "agents" / f"{name}.toml"
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text(
            f'name = "{name.replace("-", "_")}"\n'
            'description = "用于验证正式 Agent。"\n'
            f'developer_instructions = "{marker}"\n',
            encoding="utf-8",
        )
        return agent

    def test_validate_and_selective_qa_link_lifecycle(self):
        self.assertTrue(self.manager.validate(use_external=False).ok)

        self.manager.qa_link(["skill:demo-skill"])
        skill_target = self.skills_home / "demo-skill"
        agent_target = self.agents_home / "demo-agent.toml"
        self.assertTrue(skill_target.is_symlink())
        self.assertFalse(manage.path_present(agent_target))

        self.manager.qa_link(["agent:demo-agent"])
        self.assertTrue(self.agents_home.is_symlink())
        self.assertFalse(agent_target.is_symlink())
        self.assertTrue(
            manage.same_resource_content(
                agent_target, self.repo / "agents" / "demo-agent.toml"
            )
        )
        output = io.StringIO()
        with redirect_stdout(output):
            self.manager.status()
        self.assertIn("skill:demo-skill", output.getvalue())
        self.assertIn("QA 已接入", output.getvalue())

        self.manager.qa_unlink(["skill:demo-skill", "agent:demo-agent"])
        self.assertFalse(manage.path_present(skill_target))
        self.assertFalse(manage.path_present(self.agents_home))

    def test_promote_copies_selected_resources_without_linking_device(self):
        reference = self.repo / "skills" / "demo-skill" / "references" / "guide.md"
        reference.parent.mkdir()
        reference.write_text("测试参考资料。\n", encoding="utf-8")

        self.manager.promote(["skill:demo-skill", "agent:demo-agent"])

        installed_skill = self.repo / "installed" / "skills" / "demo-skill"
        installed_agent = self.repo / "installed" / "agents" / "demo-agent.toml"
        self.assertTrue(
            manage.same_resource_content(
                self.repo / "skills" / "demo-skill", installed_skill
            )
        )
        self.assertTrue(
            manage.same_resource_content(
                self.repo / "agents" / "demo-agent.toml", installed_agent
            )
        )
        self.assertFalse(manage.path_present(self.skills_home / "demo-skill"))
        self.assertFalse(manage.path_present(self.agents_home / "demo-agent.toml"))

    def test_promote_is_idempotent_and_force_updates_formal_version(self):
        self.manager.promote(["skill:demo-skill"])
        installed = self.repo / "installed" / "skills" / "demo-skill"

        output = io.StringIO()
        with redirect_stdout(output):
            self.manager.promote(["skill:demo-skill"])
        self.assertIn("内容一致", output.getvalue())

        installed_skill = installed / "SKILL.md"
        installed_skill.write_text(
            installed_skill.read_text(encoding="utf-8") + "正式区旧内容。\n",
            encoding="utf-8",
        )
        with self.assertRaises(manage.ManagerError):
            self.manager.promote(["skill:demo-skill"])
        self.assertIn("正式区旧内容", installed_skill.read_text(encoding="utf-8"))

        self.manager.promote(["skill:demo-skill"], force=True)
        self.assertTrue(
            manage.same_resource_content(
                self.repo / "skills" / "demo-skill", installed
            )
        )

    def test_promote_conflict_prevents_partial_batch_write(self):
        installed = self.add_installed_skill("demo-skill")

        with self.assertRaises(manage.ManagerError):
            self.manager.promote(["agent:demo-agent", "skill:demo-skill"])

        self.assertFalse(
            manage.path_present(
                self.repo / "installed" / "agents" / "demo-agent.toml"
            )
        )
        self.assertIn("正式版本任务", (installed / "SKILL.md").read_text("utf-8"))

    def test_promote_refuses_formal_symlink_even_with_force(self):
        external = self.repo / "external-skill"
        external.mkdir()
        (external / "SKILL.md").write_text(
            "---\n"
            "name: demo-skill\n"
            "description: 用于验证正式软链接保护。\n"
            "---\n\n"
            "不应覆盖。\n",
            encoding="utf-8",
        )
        (external / "keep.txt").write_text("保留内容。\n", encoding="utf-8")
        installed = self.repo / "installed" / "skills" / "demo-skill"
        installed.parent.mkdir(parents=True)
        installed.symlink_to(external, target_is_directory=True)

        with self.assertRaisesRegex(manage.ManagerError, "目标是软链接"):
            self.manager.promote(["skill:demo-skill"], force=True)

        self.assertTrue(installed.is_symlink())
        self.assertEqual(
            (external / "keep.txt").read_text(encoding="utf-8"), "保留内容。\n"
        )

    def test_conflict_requires_force_and_is_backed_up(self):
        conflict = self.skills_home / "demo-skill"
        conflict.mkdir(parents=True)
        (conflict / "keep.txt").write_text("user content\n", encoding="utf-8")

        with self.assertRaises(manage.ManagerError):
            self.manager.qa_link(["skill:demo-skill"])
        self.assertEqual(
            (conflict / "keep.txt").read_text(encoding="utf-8"), "user content\n"
        )

        self.manager.qa_link(["skill:demo-skill"], force=True)
        self.assertTrue(conflict.is_symlink())
        backups = list((self.codex / ".skills-research" / "backups").rglob("keep.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "user content\n")

        self.manager.qa_unlink(["skill:demo-skill"])
        self.assertTrue(conflict.is_dir())
        self.assertFalse(conflict.is_symlink())
        self.assertEqual(
            (conflict / "keep.txt").read_text(encoding="utf-8"), "user content\n"
        )

    def test_sync_and_unsync_formal_installed_collection(self):
        installed = self.add_installed_skill("active-skill")

        self.manager.sync()
        target = self.skills_home / "active-skill"
        self.assertTrue(target.is_symlink())
        self.assertEqual(manage.resolved_link(target), installed.resolve())

        output = io.StringIO()
        with redirect_stdout(output):
            self.manager.status()
        self.assertIn("正式已安装集合", output.getvalue())
        self.assertIn("已同步", output.getvalue())

        self.manager.unsync(["skill:active-skill"])
        self.assertFalse(manage.path_present(target))

    def test_agent_sync_uses_one_directory_link_and_unsyncs_as_a_unit(self):
        first = self.add_installed_agent("first-agent", "first formal")
        second = self.add_installed_agent("second-agent", "second formal")

        self.manager.sync()

        self.assertTrue(self.agents_home.is_symlink())
        self.assertEqual(
            manage.resolved_link(self.agents_home),
            (self.repo / "installed" / "agents").resolve(),
        )
        self.assertFalse((self.agents_home / "first-agent.toml").is_symlink())
        self.assertTrue(
            manage.same_resource_content(
                self.agents_home / "first-agent.toml", first
            )
        )
        self.assertTrue(
            manage.same_resource_content(
                self.agents_home / "second-agent.toml", second
            )
        )

        with self.assertRaisesRegex(manage.ManagerError, "一次选择"):
            self.manager.unsync(["agent:first-agent"])

        self.manager.unsync(["agent:first-agent", "agent:second-agent"])
        self.assertFalse(manage.path_present(self.agents_home))

    def test_agent_qa_overlay_preserves_formal_agents_and_refreshes(self):
        formal_demo = self.add_installed_agent("demo-agent", "formal demo")
        formal_other = self.add_installed_agent("other-agent", "formal other")
        development = self.repo / "agents" / "demo-agent.toml"

        self.manager.sync()
        self.manager.qa_link(["agent:demo-agent"])

        overlay = manage.resolved_link(self.agents_home)
        self.assertIsNotNone(overlay)
        self.assertNotEqual(overlay, (self.repo / "installed" / "agents").resolve())
        self.assertFalse((self.agents_home / "demo-agent.toml").is_symlink())
        self.assertTrue(
            manage.same_resource_content(
                self.agents_home / "demo-agent.toml", development
            )
        )
        self.assertTrue(
            manage.same_resource_content(
                self.agents_home / "other-agent.toml", formal_other
            )
        )
        self.assertFalse(
            manage.same_resource_content(
                self.agents_home / "demo-agent.toml", formal_demo
            )
        )
        output = io.StringIO()
        with redirect_stdout(output):
            self.manager.device_list()
        self.assertIn("仓库 QA 聚合", output.getvalue())
        self.assertIn("仓库正式同步", output.getvalue())

        development.write_text(
            development.read_text(encoding="utf-8") + "# refreshed\n",
            encoding="utf-8",
        )
        output = io.StringIO()
        with redirect_stdout(output):
            self.manager.status()
        self.assertIn("QA 聚合待刷新", output.getvalue())

        self.manager.qa_link(["agent:demo-agent"])
        self.assertTrue(
            manage.same_resource_content(
                self.agents_home / "demo-agent.toml", development
            )
        )

        self.manager.qa_unlink(["agent:demo-agent"])
        self.assertEqual(
            manage.resolved_link(self.agents_home),
            (self.repo / "installed" / "agents").resolve(),
        )
        self.assertTrue(
            manage.same_resource_content(
                self.agents_home / "demo-agent.toml", formal_demo
            )
        )

    def test_agent_directory_conflict_requires_force_and_restores_backup(self):
        self.agents_home.mkdir(parents=True)
        local = self.agents_home / "local-agent.toml"
        local.write_text("local device agent\n", encoding="utf-8")

        with self.assertRaisesRegex(manage.ManagerError, "接管整个目录"):
            self.manager.qa_link(["agent:demo-agent"])
        self.assertEqual(local.read_text(encoding="utf-8"), "local device agent\n")
        self.assertFalse(manage.path_present(self.manager.agent_overlay_source))

        self.manager.qa_link(["agent:demo-agent"], force=True)
        self.assertTrue(self.agents_home.is_symlink())
        backups = list(
            (self.codex / ".skills-research" / "backups").rglob(
                "local-agent.toml"
            )
        )
        self.assertEqual(len(backups), 1)

        self.manager.qa_unlink(["agent:demo-agent"])
        self.assertTrue(self.agents_home.is_dir())
        self.assertFalse(self.agents_home.is_symlink())
        self.assertEqual(
            (self.agents_home / "local-agent.toml").read_text(encoding="utf-8"),
            "local device agent\n",
        )

    def test_formal_agent_directory_force_backup_is_restored_on_unsync(self):
        self.add_installed_agent("formal-agent")
        self.agents_home.mkdir(parents=True)
        local = self.agents_home / "local-agent.toml"
        local.write_text("local before formal sync\n", encoding="utf-8")

        with self.assertRaisesRegex(manage.ManagerError, "接管整个目录"):
            self.manager.sync()

        self.manager.sync(force=True)
        self.assertEqual(
            manage.resolved_link(self.agents_home),
            (self.repo / "installed" / "agents").resolve(),
        )

        self.manager.unsync(["agent:formal-agent"])
        self.assertTrue(self.agents_home.is_dir())
        self.assertFalse(self.agents_home.is_symlink())
        self.assertEqual(
            (self.agents_home / "local-agent.toml").read_text(encoding="utf-8"),
            "local before formal sync\n",
        )

    def test_agent_directory_drift_blocks_qa_unlink(self):
        self.manager.qa_link(["agent:demo-agent"])
        self.agents_home.unlink()
        self.agents_home.mkdir()
        (self.agents_home / "keep.toml").write_text("drift\n", encoding="utf-8")

        with self.assertRaisesRegex(manage.ManagerError, "目录软链接"):
            self.manager.qa_unlink(["agent:demo-agent"])
        self.assertEqual(
            (self.agents_home / "keep.toml").read_text(encoding="utf-8"),
            "drift\n",
        )

    def test_manifest_v2_is_not_accepted(self):
        self.manager.manifest_path.parent.mkdir(parents=True)
        self.manager.manifest_path.write_text(
            '{"version": 2, "resources": []}\n', encoding="utf-8"
        )

        with self.assertRaisesRegex(manage.ManagerError, "不支持的管理清单"):
            self.manager.status()

    def test_qa_temporarily_overrides_and_restores_formal_resource(self):
        installed = self.add_installed_skill("demo-skill")
        target = self.skills_home / "demo-skill"
        development = self.repo / "skills" / "demo-skill"

        self.manager.sync()
        self.assertEqual(manage.resolved_link(target), installed.resolve())

        self.manager.qa_link(["skill:demo-skill"])
        self.assertEqual(manage.resolved_link(target), development.resolve())
        output = io.StringIO()
        with redirect_stdout(output):
            self.manager.status()
        self.assertIn("QA 临时覆盖", output.getvalue())

        self.manager.qa_unlink(["skill:demo-skill"])
        self.assertEqual(manage.resolved_link(target), installed.resolve())

    def test_formal_force_backup_survives_qa_and_is_restored_on_unsync(self):
        installed = self.add_installed_skill("demo-skill")
        target = self.skills_home / "demo-skill"
        target.mkdir(parents=True)
        (target / "keep.txt").write_text("original device resource\n", encoding="utf-8")

        self.manager.sync(force=True)
        self.assertEqual(manage.resolved_link(target), installed.resolve())
        self.manager.qa_link(["skill:demo-skill"])
        self.manager.qa_unlink(["skill:demo-skill"])
        self.assertEqual(manage.resolved_link(target), installed.resolve())

        self.manager.unsync(["skill:demo-skill"])
        self.assertTrue(target.is_dir())
        self.assertFalse(target.is_symlink())
        self.assertEqual(
            (target / "keep.txt").read_text(encoding="utf-8"),
            "original device resource\n",
        )

    def test_drift_blocks_qa_unlink(self):
        self.manager.qa_link(["skill:demo-skill"])
        skill_target = self.skills_home / "demo-skill"
        skill_target.unlink()
        skill_target.mkdir()
        (skill_target / "keep.txt").write_text("device content\n", encoding="utf-8")

        with self.assertRaises(manage.ManagerError):
            self.manager.qa_unlink(["skill:demo-skill"])
        self.assertEqual(
            (skill_target / "keep.txt").read_text(encoding="utf-8"),
            "device content\n",
        )

    def test_device_list_is_read_only_and_separates_existing_resources(self):
        local_skill = self.skills_home / "local-skill"
        local_skill.mkdir(parents=True)
        (local_skill / "SKILL.md").write_text(
            "---\n"
            "name: local-skill\n"
            "description: 用于验证设备盘点。\n"
            "---\n\n"
            "执行盘点测试。\n",
            encoding="utf-8",
        )
        self.agents_home.mkdir(parents=True)
        local_agent = self.agents_home / "local-agent.toml"
        local_agent.write_text('name = "local_agent"\n', encoding="utf-8")

        output = io.StringIO()
        with redirect_stdout(output):
            self.manager.device_list()
        self.assertIn("local-skill", output.getvalue())
        self.assertIn("local-agent", output.getvalue())
        self.assertIn("设备既有", output.getvalue())
        self.assertTrue(local_skill.is_dir())
        self.assertTrue(local_agent.is_file())
        self.assertFalse(self.manager.manifest_path.exists())

    def test_adopt_moves_device_resource_into_formal_collection_and_links_it(self):
        local_skill = self.skills_home / "local-skill"
        local_skill.mkdir(parents=True)
        (local_skill / "SKILL.md").write_text(
            "---\n"
            "name: local-skill\n"
            "description: 用于验证显式纳管。\n"
            "---\n\n"
            "执行纳管测试。\n",
            encoding="utf-8",
        )

        self.manager.adopt("skill:local-skill")

        repository_skill = self.repo / "installed" / "skills" / "local-skill"
        self.assertTrue(repository_skill.is_dir())
        self.assertTrue(local_skill.is_symlink())
        self.assertEqual(manage.resolved_link(local_skill), repository_skill.resolve())
        output = io.StringIO()
        with redirect_stdout(output):
            self.manager.device_list()
        self.assertIn("仓库正式同步", output.getvalue())

    def test_adopt_single_device_agent_takes_over_parent_directory(self):
        self.agents_home.mkdir(parents=True)
        local_agent = self.agents_home / "local-agent.toml"
        local_agent.write_text(
            'name = "local_agent"\n'
            'description = "用于验证 Agent 纳管。"\n'
            'developer_instructions = "只执行测试任务。"\n',
            encoding="utf-8",
        )

        self.manager.adopt("agent:local-agent")

        repository_agent = (
            self.repo / "installed" / "agents" / "local-agent.toml"
        )
        self.assertTrue(repository_agent.is_file())
        self.assertTrue(self.agents_home.is_symlink())
        self.assertEqual(
            manage.resolved_link(self.agents_home),
            (self.repo / "installed" / "agents").resolve(),
        )
        self.assertFalse((self.agents_home / "local-agent.toml").is_symlink())
        self.assertTrue(
            manage.same_resource_content(
                self.agents_home / "local-agent.toml", repository_agent
            )
        )

    def test_adopt_migrates_legacy_skill_to_standard_link_location(self):
        legacy_skill = self.codex / "skills" / "legacy-skill"
        legacy_skill.mkdir(parents=True)
        (legacy_skill / "SKILL.md").write_text(
            "---\n"
            "name: legacy-skill\n"
            "description: 用于验证旧目录迁移。\n"
            "---\n\n"
            "执行旧目录迁移测试。\n",
            encoding="utf-8",
        )

        self.manager.adopt("skill:legacy-skill")

        repository_skill = self.repo / "installed" / "skills" / "legacy-skill"
        standard_link = self.skills_home / "legacy-skill"
        self.assertFalse(manage.path_present(legacy_skill))
        self.assertEqual(manage.resolved_link(standard_link), repository_skill.resolve())

    def test_qa_operations_require_explicit_resources(self):
        with self.assertRaises(manage.ManagerError):
            self.manager.promote([])
        with self.assertRaises(manage.ManagerError):
            self.manager.qa_link([])
        with self.assertRaises(manage.ManagerError):
            self.manager.qa_unlink([])
        with self.assertRaises(manage.ManagerError):
            self.manager.unsync([])


if __name__ == "__main__":
    unittest.main()
