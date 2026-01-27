"""
This tool generates NVDA extensions.

Builders:

- NVDAAddon: Creates a .nvda-addon zip file. Requires the `excludePatterns` environment variable.
- NVDAManifest: Creates the manifest.ini file.
- NVDATranslatedManifest: Creates the manifest.ini file with only translated information.
- md2html: Build HTML from Markdown

The following environment variables are required to create the manifest:

- addon_info: .typing.AddonInfo
- brailleTables: .typings.BrailleTables
- symbolDictionaries: .typings.SymbolDictionaries

The following environment variables are required to build the HTML:

- moFile: str | pathlib.Path | None
- mdExtensions: list[str]
- addon_info: .typings.AddonInfo

"""

from typing import Any
from SCons.Script import Environment, Builder

from .addon import createAddonBundleFromPath
from .manifests import generateManifest, generateTranslatedManifest
from .docs import md2html


def generate(env: Environment):
	env.SetDefault(excludePatterns=tuple())

	def addon_action(target: list[Any], source: list[Any], env: Any):
		return (
			createAddonBundleFromPath(
				source[0].abspath,
				target[0].abspath,
				env["excludePatterns"],
			)
			and None
		)

	def addon_string(target: list[Any], source: list[Any], env: Any):
		return f"Generating Addon {target[0]}"

	addonAction = env.Action(addon_action, addon_string)
	env["BUILDERS"]["NVDAAddon"] = Builder(
		action=addonAction,
		suffix=".nvda-addon",
		src_suffix="/",
	)

	env.SetDefault(brailleTables={})
	env.SetDefault(symbolDictionaries={})

	def manifest_action(target: list[Any], source: list[Any], env: Any):
		return (
			generateManifest(
				source[0].abspath,
				target[0].abspath,
				addon_info=env["addon_info"],
				brailleTables=env["brailleTables"],
				symbolDictionaries=env["symbolDictionaries"],
			)
			and None
		)

	def manifest_string(target: list[Any], source: list[Any], env: Any):
		return f"Generating manifest {target[0]}"

	manifestAction = env.Action(manifest_action, manifest_string)
	env["BUILDERS"]["NVDAManifest"] = Builder(
		action=manifestAction,
		suffix=".ini",
		src_siffix=".ini.tpl",
	)

	def translated_manifest_action(target: list[Any], source: list[Any], env: Any):
		return (
			generateTranslatedManifest(
				source[1].abspath,
				target[0].abspath,
				mo=source[0].abspath,
				addon_info=env["addon_info"],
				brailleTables=env["brailleTables"],
				symbolDictionaries=env["symbolDictionaries"],
			)
			and None
		)

	def translated_manifest_string(target: list[Any], source: list[Any], env: Any):
		return f"Generating translated manifest {target[0]}"

	translatedManifestAction = env.Action(
		translated_manifest_action,
		translated_manifest_string,
	)

	env["BUILDERS"]["NVDATranslatedManifest"] = Builder(
		action=translatedManifestAction,
		suffix=".ini",
		src_siffix=".ini.tpl",
	)

	env.SetDefault(mdExtensions={})

	def md_action(target: list[Any], source: list[Any], env: Any):
		return (
			md2html(
				source[0].path,
				target[0].path,
				moFile=env["moFile"].path if env["moFile"] else None,
				mdExtensions=env["mdExtensions"],
				addon_info=env["addon_info"],
			)
			and None
		)

	def md_string(target: list[Any], source: list[Any], env: Any):
		return f"Generating {target[0]}"

	mdAction = env.Action(md_action, md_string)
	env["BUILDERS"]["md2html"] = env.Builder(
		action=mdAction,
		suffix=".html",
		src_suffix=".md",
	)


def exists():
	return True
