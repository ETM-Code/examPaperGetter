# ExamPaperGetter

An automated tool for downloading and organizing exam papers from educational institutions (works for the University of Galway , may work for other universities with minor modifications (changing links, etc.)). This tool uses Puppeteer to navigate through exam paper repositories, download PDFs, and organize and combine them by subject.

## Features

- Automated exam paper downloading using Puppeteer with stealth mode
- PDF merging capabilities for consolidated subject files
- Configurable subject list through `subjects.txt`
- Ad-blocking functionality for faster downloads
- Automatic file organization by subject

## Prerequisites

- Node.js (Latest LTS version recommended)
- npm (comes with Node.js)

## Installation

1. Clone this repository:
```bash
git clone [your-repo-url]
cd exampapergetter
```

2. Install dependencies:
```bash
npm install
```

## Configuration

1. Create a `subjects.txt` file in the root directory with your subjects in the following format:
```
SUBJECT_CODE:Subject Name
```
For example:
```
EE2101:Communications and Networking Foundations
```

## Usage

Run the script using:
```bash
node examScraper.js
```

The script will:
1. Read subjects from `subjects.txt`
2. Navigate to the exam paper repository
3. Download relevant PDFs for each subject
4. Merge PDFs into consolidated files by subject
5. Organize everything in a structured directory

## Dependencies

- `puppeteer-extra`: Enhanced version of Puppeteer with plugin support
- `pdf-lib`: PDF manipulation library
- `puppeteer-extra-plugin-stealth`: Helps avoid detection
- `puppeteer-extra-plugin-adblocker`: Blocks ads for faster navigation
- `puppeteer-extra-plugin-user-preferences`: Manages browser preferences
- `node-fetch`: Fetch API implementation for Node.js

## Project Structure

```
examPaperGetter/
├── examScraper.js    # Main script
├── subjects.txt      # Subject configuration file
├── package.json      # Project dependencies
└── README.md         # This file
```

## License

ISC

## Author

Eoghan Collins

## Contributing

Feel free to submit issues and enhancement requests! 