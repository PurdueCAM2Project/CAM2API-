from rest_framework import serializers
from CAM2API.models import Camera, IP, Non_IP
from django.core.exceptions import ValidationError
from django.contrib.gis.geos import GEOSGeometry
import re 
import geocoder
import sys


from CAM2API.models import Account

class IPSerializer(serializers.ModelSerializer):

	class Meta:
		model = IP
		fields = ('ip','port')

	def create(self, validated_data):
		return IP.objects.create(**validated_data)

	def to_internal_value(self, data):
		ret = {}
		errors = []
		for field in self.fields:  #self_writable_field  self.fields returns a dict {'ip': CharFied}   self.fieldss.values.field_name returns 'ip'
			try:
				validate_method = getattr(self, 'validate_'+field)
			except AttributeError:
				print("The IP calss validation method {} does not exist" .format('validate_'+field))
				validate_method = None

			if validate_method is not None:
				try:
					validated_value = validate_method(data.get(field))
				except ValidationError as exc: 
					errros.append(exc.details) 
				else:
					ret[field] = validated_value
					errors.append({})
			else:
				ret[field] = data.get(field,None)

		if any(errors):
			raise ValidationError(errors)
		else:
			return ret 

	def to_representation(self, instance):
		ret = {}
		for f in self.fields.values():
			value = getattr(instance, f.field_name)  #f.field_name returns 'ip','port', 
			ret[f.field_name] = f.to_representation(value)
		return ret 


	def validate_ip(self,value):
		pattern = r'^\d+.\d+.\d+.\d+$'
		if re.search(pattern,value) is None:
			raise serializers.ValidationError('This is not valid IP address')
		return value

	def validate_port(self,value):
		if not str(value).isdigit():
			raise serializers.ValidationError('This is not valid port')
		return value

	def validate(self, data):
		pass

class NonIPSerializer(serializers.ModelSerializer):
	class Meta:
		model = Non_IP
		fields = ('url',)

class CameraSerializer(serializers.ModelSerializer):
	retrieval_model = serializers.SerializerMethodField()

	class Meta:
		model = Camera
		fields = ('pk', 'camera_id', 'city' ,'state', 'country', 'retrieval_model','lat','lng','lat_lng','source','source_url',
			'date_added','last_updated','camera_type','description','is_video','framerate',
			'outdoors','indoors','traffic','inactive','resolution_w','resolution_h')
		extra_kwargs = {'lat_lng':{'write_only':True}}
		

	def create(self, validated_data):   #Deserialize
		print("Create")
		retrieval_data = validated_data.pop('retrieval_model')
		if 'url' in retrieval_data.keys():
			retrieval_model = Non_IP.objects.create(**retrieval_data)  #create Non_IP object if "url" exists in request 
		else:
			retrieval_model = IP.objects.create(**retrieval_data)	 #create IP object otherwise 
		camera = Camera.objects.create(retrieval_model=retrieval_model, **validated_data)
		return camera

	def update(self, instance, validated_data):  #Deserialize
		print("Update")
		retrieval_data = validated_data.pop('retrieval_model')
		retrieval_instance = instance.retrieval_model
		for key, value in validated_data.items():
			if value is not None:
				setattr(instance,key,value)
		setattr(instance,'lat_lng', self.get_lat_lng(validated_data))
		for key, value in retrieval_data.items():
			setattr(retrieval_instance, key, value)
		retrieval_instance.save()
		instance.save()
		return instance

	def to_internal_value(self, data):  #Deserialize
		ret = {}
		errors = []
		for field in self.fields:
			if field == "retrieval_model":
				retrieval_model_data = data.get('retrieval_model', None)      #extract "retrieval_model" and process it later based on which base Serializer to exploit 
			elif field == "lat_lng":	
				ret[field] = self.get_lat_lng(data)					#create GEOSGeomoetry object 
			else:
				
				try:
					validate_method = getattr(self, 'validate_'+field)
				except AttributeError:
					validate_method = None

				if validate_method is not None:
					try:
						validated_value = validate_method(data.get(field,None))
					except ValidationError as exc:
						errors.append(exc.detials)
					else:
						ret[field] = validated_value
						errors.append({})
				else:
					ret[field] = data.get(field,None)
		if ret is not None:
			if 'ip' in retrieval_model_data.keys():
				a = IPSerializer(data=retrieval_model_data)     #use IPSerializer as base serializer if "ip" exists in request
			else:	
				a = NonIPSerializer(data=retrieval_model_data)   	#use NonIPSerializer otherwise 
			ret['retrieval_model'] = a.to_internal_value(retrieval_model_data)
		
		if any(errors):
			raise ValidationError(errors)
		else:
			return ret

	def to_representation(self,instance):   #Serialize
		ret = {}
		fields = self._readable_fields
		for field in fields:
			value = getattr(instance, field.field_name)
			ret[field.field_name] = field.to_representation(value) 
		return ret

	def get_retrieval_model(self,instance):  #Serialize
		if isinstance(instance,IP):
			return IPSerializer(instance).data   		#Use IPSerializer if retrieval_model object is a IP object()
		else:
			return NonIPSerializer(instance).data 		#Use NonIPSerializer if retrieval_model object is Non_IP object
	
	def validate_city(self,value):
		pattern = r'[a-zA-Z]+'
		if re.search(pattern,str(value)) is None:
			raise serializers.ValidationError("This is not a valid city name")
		return value
	
	def validate_state(self,value):
		pattern = r'[a-zA-Z]+'
		if re.search(pattern,str(value)) is None:
			raise serializers.ValidationError("This is not a valid state name")
		return value

	def validate_country(self,value):
		pattern = r'[a-zA-Z]+'
		if re.search(pattern,str(value)) is None:
			raise serializers.ValidationError("This is not a valid country name")
		return value	
	
	def validate_resolution_w(self, value):
		if int(value) <= 0:
			raise serializers.ValidationError("This is not a valid resolution for width")
		return value

	def validate_resolution_h(self, value):
		if int(value) <= 0:
			raise serializers.ValidationError("This is not a valid resolution for height")
		return value
	
	def get_lat_lng(self, data):
		lat_lng = '{{ "type": "Point", "coordinates": [ {}, {} ] }}'.format(data.get('lat',None), data.get('lng',None))
		lat_lng = GEOSGeometry(lat_lng)
		return lat_lng

	def validate(self, data):
		assert "lat" and "lng" in data.keys()
		geo_checker = geocoder.google([data["lat"], data["lng"]], method="reverse")
		geo_checker_result = geo_checker.json
		print(geo_checker.json)
		if geo_checker_result["status"] == "OK":
			try:
				if data.get("city", None) is not None:
					assert data["city"] == geo_checker_result["city"]
				if data.get("state", None) is not None:
					assert data["state"] == geo_checker_result["state"]
				if data.get("country", None) is not None:
					assert data["country"] == geo_checker_result["country"]
			except AssertionError:
<<<<<<< HEAD
				raise serializers.ValidationError("Invalid")
=======
				raise AssertionError("Invalid location data")
				print("Invalid")
>>>>>>> 48305742750fa001aa86f5b75965ec75160d3719
		return data 


# class CameraSerializer(serializers.ModelSerializer):
# 	
	    #class Meta:
# 		model = Camera
# 		fields = ('camera_id','city','state','country','lat', 'lng','lat_lng','source','source_url',\
# 			'date_added','last_updated','camera_type','description','is_video','framerate',\
# 			'outdoors','indoors','traffic','inactive','resolution_w','resolution_h', 'content_type', 'object_id', 'retrieval_model')
# 		# Need to searialize 'retrieval_model'


# class CameraSerializer(serializers.Serializer):
# 	camera_id = serializers.IntegerField() # id from old database 
# 	# Geography: 
# 	city = serializers.CharField()
# 	state = serializers.CharField()
# 	country = serializers.CharField()
# 	lat = serializers.FloatField()
# 	lng = serializers.FloatField()
# 	# lat_lng = serializers.GeometryField() # Sets geometry field points to geography in postgis
	
# 	# Source Information:
# 	source = serializers.CharField()
# 	source_url = serializers.CharField() # URL of the provider of the source (NOT for image data!)
# 	# Time Information:
# 	date_added = serializers.DateTimeField()
# 	last_updated = serializers.DateTimeField() # Last known time a snapshot was downloaded
# 	# Camera Types (Non_ip or IP)
# 	camera_type = serializers.CharField()
# 	# More Info:
# 	description = serializers.CharField() # Description of the camera
# 	is_video = serializers.BooleanField() # True if camera is a video stream 
# 	framerate = serializers.FloatField() # Frame rate of the camera if known
# 	outdoors = serializers.NullBooleanField() # True if camera is outdoors Null if unknown.
# 	indoors = serializers.NullBooleanField() # True if the camera is indoors Null if unknown.
# 	traffic = serializers.NullBooleanField() # True if the camera is a traffic camera Null if unknown.
# 	inactive = serializers.NullBooleanField() # True if data cannot be accessed from the camera Null if unknown.
# 	resolution_w = serializers.IntegerField() # Resolution width determined automatically 
# 	resolution_h = serializers.IntegerField() # Resolution height determined automatically 
# 	# created_by = # Token for user who added the camera to the database

# 	# Image Retrieval objects:
# 	# For more information see https://docs.djangoproject.com/en/1.10/ref/contrib/contenttypes/#generic-relations

# 	# content_type = serializers.ForeignKey(ContentType, on_delete=serializers.CASCADE)
# 	# object_id = models.PositiveIntegerField()
# 	retrieval_model = GenericForeignKey()

	# def create(self, validated_data):
	# 	"""
	# 	Create and return a new 'Camera' instance, given the validated data.
	# 	"""
	# 	return Camera.objects.create(**validated_data)

# 	def update(self, instance, validated_data):
# 		"""
# 		Update and return an existing 'Camera' instance, given the validated data.
# 		"""
# 		instance.camera_id = validated_data.get('camera_id', instance.camera_id) # id from old database 
# 		# Geography: 
# 		instance.city = validated_data.get('city', instance.city)
# 		instance.state = validated_data.get('state', instance.state)
# 		instance.country = validated_data.get('country', instance.country)
# 		# Source Information:
# 		instance.source = validated_data.get('source', instance.source)
# 		instance.source_url = validated_data.get('source_url', instance.source_url) # URL of source (Not for image data!)
# 		# Time Information:
# 		instance.date_added = validated_data.get('date_added', instance.date_added)
# 		instance.last_updated = validated_data.get('last_updated', instance.last_updated) # Last known time a snapshot was downloaded
# 		# Camera Types (Non_ip or IP)
# 		instance.camera_type = validated_data.get('camera_type', instance.camera_type) 
# 		# More Info:
# 		instance.description = validated_data.get('description', instance.description) # Description of the camera
# 		instance.is_video = validated_data.get('is_video', instance.is_video) # True if camera is a video stream 
# 		instance.framerate = validated_data.get('framerate', instance.framerate) # Frame rate of the camera if known
# 		instance.outdoors = validated_data.get('outdoors', instance.outdoors) # True if camera is outdoors Null if unknown.
# 		instance.indoors = validated_data.get('indoors', instance.indoors) # True if the camera is indoors Null if unknown.
# 		instance.traffic = validated_data.get('traffic', instance.traffic) # True if the camera is a traffic camera Null if unknown.
# 		instance.inactive = validated_data.get('inactive', instance.inactive) # True if data cannot be accessed from the camera Null if unknown.
# 		instance.resolution_w = validated_data.get('resolution_w', instance.resolution_w) # Resolution width determined automatically 
# 		instance.resolution_h = validated_data.get('resolution_h', instance.resolution_h) # Resolution height determined automatically 

# 		instance.save()
# 		return instance

class AccountSerializer(serializers.ModelSerializer):
	class Meta:
		model = Account
		fields = ('username', 'email', 'password', )
		extra_kwargs = {'password': {'write_only': True}}

	def create(self, validated_data):
		password = validated_data.pop('password', None)
		email = validated_data.pop('email', None)
		return Account.objects.create_user(email, password, **validated_data)



class LoginSerializer(serializers.ModelSerializer):
	class Meta:
		model = Account
		fields = ('username', 'email', 'password', )
		extra_kwargs = {'password': {'write_only': True}}

	def validate(self, data):
		print("HERE")
		username = data.get('username', None)
		password = data.get('password', None)
		if username is None or password is None:
			raise ValidationError("Login failed")

		accounts = Account.objects.filter(username=username)

		if accounts.exists():
			account = accounts.first()
			result = account.check_password(password)
			if not result:
				raise ValidationError("Password is Incorrect")
			else:
				return data
		else:
			raise ValidationError("Username is Invalid")

