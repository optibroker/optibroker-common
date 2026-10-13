Hello ${user.firstName!user.username},

We received a request to reset your ${msg("companyName")} account password.
Use this link to set a new password:

${link}

This link expires in ${linkExpiration!} minutes.
If you didn’t request this, you can safely ignore this email.

— The ${msg("companyName")} Team
