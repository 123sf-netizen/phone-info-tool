import base64
import subprocess
import tempfile
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class StartupPreflightTests(unittest.TestCase):
    def test_existing_new_and_incomplete_states(self):
        script = ". ./local-app/startup_preflight.ps1; Get-StartupMode $true $true; Get-StartupMode $false $false; try { Get-StartupMode $true $false } catch { 'blocked' }; try { Get-StartupMode $false $true } catch { 'blocked' }"
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded], cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertEqual(result.stdout.decode().splitlines(), ['existing', 'new', 'blocked', 'blocked'])

    def test_startup_workflow_with_mocked_docker(self):
        source = ROOT / 'local-app'
        for has_env, has_volume, expected in [(False, False, 'new'), (True, True, 'existing'), (True, False, 'blocked'), (False, True, 'blocked')]:
            with self.subTest(has_env=has_env, has_volume=has_volume), tempfile.TemporaryDirectory() as directory:
                target = Path(directory)
                shutil.copy(source / '启动项目.ps1', target / 'start.ps1')
                shutil.copy(source / 'startup_preflight.ps1', target / 'startup_preflight.ps1')
                if has_env:
                    (target / '.env').write_text('MYSQL_PASSWORD=test\nMYSQL_ROOT_PASSWORD=test\nADMIN_TOKEN=test\n', encoding='ascii')
                volume = '$true' if has_volume else '$false'
                script = """
$global:volumeExists = VOLUME
$global:created = $false
function global:docker {
  if ($args[0] -eq 'info') { $global:LASTEXITCODE=0; return 'mock' }
  if ($args[0] -eq 'volume' -and $args[1] -eq 'ls') { $global:LASTEXITCODE=0; if($global:volumeExists){return 'local-app_phone_mysql'}; return }
  if ($args[0] -eq 'volume' -and $args[1] -eq 'create') { $global:created=$true; $global:LASTEXITCODE=0; return 'mock' }
  if ($args[0] -eq 'compose') { $global:LASTEXITCODE=0; return }
  throw 'unexpected docker invocation'
}
try { & './start.ps1' | Out-Null; if($global:created){'new'}else{'existing'} } catch { 'blocked' }
""".replace('VOLUME', volume)
                encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
                result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded], cwd=target, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                self.assertEqual(result.stdout.decode().splitlines()[-1], expected)
                self.assertEqual((target / '.env').exists(), has_env or expected == 'new')


if __name__ == '__main__':
    unittest.main()
