import jwt
token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6Imp2bmZlb0BnbWFpbC5jb20iLCJyb2xlIjoidGVhY2hlciIsImV4cCI6MTc4OTk4NDIzMn0.71Hxxqw5uZTrr0Fdbem27otPpx6j4gHwPCyknTL4zIc'
try:
    decoded = jwt.decode(token, 'vyom_super_secret_jwt_key_2026', algorithms=['HS256'])
    print('Decoded successfully:', decoded)
except Exception as e:
    print('Decode failed:', str(e))
