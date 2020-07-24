# dRPG downloads and keeps your purchases from DriveThruRPG up to date

## How to use it

1. Go to [your account settings](https://www.drivethrurpg.com/account_edit.php)
   and generate a new application key.
2. Copy the key and run the script with: `DRPG_TOKEN=<YOUR_TOKEN> python drpg.py `.
3. Now just sit, relax and wait. Initial synchronization may take a while.  On
   consecutive runs the script will download only changed files.

## Advanced options

By default the script does not compare files by md5 checksum to save time. You
can turn it on by setting `DRPG_PRECISELY=true`.

You can change a log level by setting `DRPG_LOGLEVEL=<YOUR_LOG_LEVEL>`. Choices
are DEBUG, INFO, WARNING, FATAL.
