# VB.NET client tests

**BuildCheck** compiles `VbOcrClient.vb` and `VbOcrScanForm.vb` as an old project would:
.NET Framework 2.0 with VB 9 (Visual Studio 2008) and .NET Framework 4.5 with VB 15
(Visual Studio 2017), Option Strict On, warnings as errors. Needs only the .NET SDK
(Windows, macOS or Linux):

```
dotnet build clients/vbnet/tests/BuildCheck
```

**ClientTest** runs `VbOcrClient` against a running server, with test invoices:

```
python tests/make_test_files.py test-files
python -m vbocr serve --port 5077                 (in another window)
dotnet run --project clients/vbnet/tests/ClientTest -- http://127.0.0.1:5077 test-files
```

Add the access key as a third argument when the server has `server.api_key` set. Both run
in the GitHub Actions workflow on Windows (`.github/workflows/ci.yml`).
