"""Create a deployment archive from an explicit source/config allowlist."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
MODULES = '''
ai_coding_demo audio_follow audio_pairing backend_network coding_organizer
concept_first_network correction_speed dimension_definition evidence_nodes
finding_boundary finding_definition finding_review finding_review_pipeline indexed_theme
interview_coding interview_facts interview_library interview_move interview_names
interview_reference_index interview_trash_api network_batches node_gates node_quality
raw_theme_source review_storage run_accounts run_cloud site_ai_guard site_app site_boundary
site_guests site_store site_worker source_search statement_comparison theme_file_io
theme_model_io theme_network theme_recovery transcript_review transcription_recovery
web_app word_cooccurrence word_topic_index
'''.split()


def bundle(destination):
    files = [ROOT / (name + '.py') for name in MODULES]
    files += [ROOT / name for name in ('requirements-cloud.txt', 'CLOUD_SETUP.md',
                                       'AI文字校订规则.txt', 'AI标点整理规则.txt',
                                       'word-cooccurrence-defaults.json',
                                       'web/index.html', 'web/account-center.html')]
    files += [p for p in (ROOT / 'web').iterdir() if p.suffix in {'.js', '.css'} and not p.name.startswith('test-')]
    if any(not p.is_file() or p.is_symlink() or p.resolve() != p for p in files):
        raise ValueError('部署所需文件缺失，或包含指向其他位置的链接')
    with ZipFile(destination, 'x', compression=ZIP_DEFLATED) as archive:
        for file in sorted(files):
            archive.write(file, file.relative_to(ROOT).as_posix())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    bundle(parser.parse_args().destination)
