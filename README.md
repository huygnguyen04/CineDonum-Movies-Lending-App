# CineDonum: Movie Cataloging and Lending Application

## Project Overview
CineDonum is a Django-based web application designed to catalog and facilitate lending of physical movies. It allows users to create accounts, browse movie collections, request to borrow movies, and manage their own collections. The application is developed as part of the CS 3240 course at University of Virginia.

## Key Features
- **User Authentication**: Secure login via Google accounts
- **User Roles**: Three distinct user types (Patrons, Librarians, and Admin)
- **Movie Catalog**: Comprehensive database of movies with details like cast, genre, and descriptions
- **Collections**: Public and private collections of movies organized by theme
- **Search Functionality**: Search for movies and collections by title or other attributes
- **Borrowing System**: Request, approve, and manage movie loans
- **Review System**: Rate and review movies
- **Notification System**: Get notifications for loan approvals, rejections, and due dates
- **AWS S3 Integration**: Cloud storage for movie images and user profile pictures

## User Types and Permissions

### Anonymous Users
- Browse public collections and movies not in collections
- View movie details and reviews
- Search public movies and collections

### Patrons
- All Anonymous user privileges
- Create personal account with profile
- Request to borrow movies
- Create public collections
- Request access to private collections
- Rate and review movies
- Manage personal borrowing history

### Librarians
- All Patron privileges
- Add, edit, and delete movies in the catalog
- Create public and private collections
- Process loan requests (approve/reject)
- Manage returns and overdue items
- View borrowing reports

### Admin
- Access to the Django admin interface
- Manage user accounts and permissions
- Database management and maintenance

## Technology Stack
- **Backend**: Django 5.0, Python 3
- **Database**: PostgreSQL
- **Cloud Storage**: AWS S3
- **Authentication**: Google OAuth
- **Deployment**: Heroku

## Heroku App Link
### [CineDonum](https://cs3240-s25-a29-eea118da5a2d.herokuapp.com/)

## Demo Accounts

### Librarian Account
- Email: movies.app.librarian@gmail.com
- Password: librarian123

### Patron Account
- Email: movies.app.patron@gmail.com
- Password: patron123

### Admin
- Username: huy1211
- Password: admin

## Installation and Setup
1. Clone this repository
2. Install required packages: `pip install -r requirements.txt`
3. Set up environment variables for:
   - Database connection
   - Google OAuth credentials
   - AWS S3 credentials
4. Run migrations: `python manage.py migrate`
5. Start development server: `python manage.py runserver`

## Contributing
This is a class project for CS 3240 at the University of Virginia. Please follow the contribution guidelines provided by the course instructors.

## License
MIT License Copyright (c) 2025 Team A-29

## Disclaimer
This system is a class project. It is not monitored for production use, and no real personal information should be submitted.

---

Project developed by Team A-29 for CS 3240 - Spring 2025 at the University of Virginia.
